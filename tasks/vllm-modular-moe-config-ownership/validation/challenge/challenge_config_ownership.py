#!/usr/bin/env python3
"""Independent fresh challenge for modular-MoE config ownership provenance.

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. It re-enters the production factory path
(FusedMoEModularMethod.make -> FusedMoEModularKernel profile forward) but
independently re-derives the ownership invariant with:

  * a fresh MoE geometry (17/112/176/6/3 vs the verifier's 19/80/144/4/2),
  * a THREE-WAY config disagreement (active layer owner != stale legacy
    quant-method copy != ambient process-global), so a kernel that reads
    either wrong source is detectable, and
  * the DP+EP role assigned to the layer whose ambient config is non-DP,
    the inverse of one verifier arrangement.

Invariant (re-derived, not copied): the modular kernel's profiling-workspace
behavior must follow the ACTIVE layer owner (layer.moe_parallel_config), never the ambient/global config
and never the stale legacy quant-method copy.

Expected outcomes are Oracle/alternative PASS and Base/wrong-owner FAIL.
Actual execution results are recorded separately in e2e-evidence.json.
"""
from __future__ import annotations

import contextlib
import json
import logging
import sys
import traceback
from types import SimpleNamespace

import torch

import vllm.model_executor.layers.fused_moe.fused_moe_modular_method as method_module
import vllm.model_executor.layers.quantization.utils.flashinfer_utils as flashinfer_utils
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.config import (
    FUSED_MOE_UNQUANTIZED_CONFIG,
    FusedMoEParallelConfig,
    FusedMoEConfig,
)
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
from vllm.model_executor.layers.fused_moe.modular_kernel import FusedMoEModularKernel
from vllm.model_executor.layers.fused_moe.prepare_finalize import MoEPrepareAndFinalizeNoEP
from vllm.v1.worker.workspace import init_workspace_manager

# Fresh geometry, independent of the verifier's 19/80/144/4/2.
EXPERTS, TOKENS, HIDDEN, INTERMEDIATE, TOP_K = 6, 17, 112, 176, 3


def fused_config(dp_size: int, use_ep: bool) -> FusedMoEParallelConfig:
    return FusedMoEParallelConfig(
        tp_size=1, pcp_size=1, dp_size=dp_size,
        ep_size=dp_size if use_ep else 1,
        tp_rank=0, pcp_rank=0, dp_rank=0, ep_rank=0,
        use_ep=use_ep, all2all_backend="allgather_reducescatter",
    )


def ambient_config(dp_size: int, use_ep: bool) -> ParallelConfig:
    return ParallelConfig(data_parallel_size=dp_size, enable_expert_parallel=use_ep)


def make_components():
    return MoEPrepareAndFinalizeNoEP(), TritonExperts(FUSED_MOE_UNQUANTIZED_CONFIG)


def layer(owner, ambient):
    return SimpleNamespace(
        moe_config=FusedMoEConfig(
            num_experts=EXPERTS, experts_per_token=TOP_K,
            hidden_dim=HIDDEN, num_local_experts=EXPERTS,
            moe_parallel_config=owner, in_dtype=torch.bfloat16,
            max_num_tokens=16384,
        ),
        moe_parallel_config=owner,
        vllm_config=SimpleNamespace(parallel_config=ambient),
        shared_experts_stream=None,
    )


def kernel_through_factory(moe_layer, process_global, legacy_owner):
    original_method = method_module.FusedMoEModularMethod
    prepare, experts = make_components()

    class ExistingQuantMethod:
        moe = SimpleNamespace(moe_parallel_config=legacy_owner,
                              dp_size=legacy_owner.dp_size, use_ep=legacy_owner.use_ep)

        @staticmethod
        def select_gemm_impl(prepare_finalize, active_layer):
            return experts

    method_module.FusedMoEModularMethod = lambda old, kernel: kernel
    try:
        with set_current_vllm_config(VllmConfig(parallel_config=process_global)):
            kernel = original_method.make(moe_layer, ExistingQuantMethod(), prepare, None)
    finally:
        method_module.FusedMoEModularMethod = original_method
    assert isinstance(kernel, FusedMoEModularKernel)
    return kernel, experts


def make_inputs():
    torch.manual_seed(30282)
    x = torch.randn(TOKENS, HIDDEN, device="cuda", dtype=torch.bfloat16)
    w1 = torch.randn(EXPERTS, 2 * INTERMEDIATE, HIDDEN, device="cuda", dtype=torch.bfloat16)
    w2 = torch.randn(EXPERTS, HIDDEN, INTERMEDIATE, device="cuda", dtype=torch.bfloat16)
    logits = torch.randn(TOKENS, EXPERTS, device="cuda")
    weights, ids = torch.topk(logits, TOP_K, dim=-1)
    return x, w1, w2, torch.softmax(weights, dim=-1), ids


def run_cuda(kernel, inputs, *, profile=False, workspace=None):
    x, w1, w2, weights, ids = inputs
    ctx = set_forward_context(None, VllmConfig()) if profile else contextlib.nullcontext()
    with observe_workspace_bytes(workspace, inputs), ctx:
        out = kernel(hidden_states=x, w1=w1, w2=w2, topk_weights=weights,
                     topk_ids=ids, inplace=False, global_num_experts=EXPERTS)
    torch.cuda.synchronize()
    assert out.is_cuda and out.shape == x.shape
    assert bool(torch.isfinite(out).all()) and out.abs().sum().item() > 0
    return out


@contextlib.contextmanager
def observe_workspace_bytes(observed, inputs):
    # Observe actual CUDA temporaries and views through PyTorch, independently
    # of the candidate's cache classes and allocation helper names.
    if observed is None:
        yield
        return
    from torch.utils._python_dispatch import TorchDispatchMode
    excluded = {t.untyped_storage().data_ptr() for t in inputs}
    class WorkspaceScope(TorchDispatchMode):
        def __torch_dispatch__(self, func, types, args=(), kwargs=None):
            result = func(*args, **(kwargs or {}))
            def record(value):
                if isinstance(value, torch.Tensor):
                    if value.is_cuda and value.untyped_storage().data_ptr() not in excluded:
                        observed.append(value.numel() * value.element_size())
                elif isinstance(value, (tuple, list)):
                    for item in value:
                        record(item)
                elif isinstance(value, dict):
                    for item in value.values():
                        record(item)
            record(result)
            return result
    with WorkspaceScope():
        yield




def workspace_bytes(observed):
    assert observed, "production workspace allocation was not reached"
    return max(observed)




def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    assert torch.cuda.get_device_capability(0) == (8, 0), "challenge targets A100 (sm80)"
    init_workspace_manager(torch.device("cuda:0"))
    inputs = make_inputs()

    stages, failures = {}, {}
    try:
        # Baseline compatibility path must not warn about missing config.
        warnings = []

        class Capture(logging.Handler):
            def emit(self, record):
                warnings.append(record.getMessage())

        handler = Capture()
        # Prove this handler sees the real diagnostic, then clear the control.
        import vllm.config.vllm as config_module
        config_module._current_vllm_config = None
        config_module.get_cached_compilation_config.cache_clear()
        logger = logging.getLogger("vllm.config.vllm")
        logger.addHandler(handler)
        try:
            config_module.get_current_vllm_config()
        finally:
            logger.removeHandler(handler)
        assert any("Current vLLM config is not set" in m for m in warnings), "warning capture control failed"
        warnings.clear()
        logging.getLogger("vllm.config.vllm").addHandler(handler)
        try:
            baseline = FusedMoEModularKernel(*make_components())
            baseline_out = run_cuda(baseline, inputs)
        finally:
            logging.getLogger("vllm.config.vllm").removeHandler(handler)
        assert not any("Current vLLM config is not set" in m for m in warnings)
        stages["baseline"] = {"norm": float(baseline_out.float().norm())}

        # THREE-WAY disagreement. The DP+EP layer's ambient is deliberately
        # non-DP; its legacy quant copy is a third, distinct config. Only the
        # active owner is DP+EP, so only active-owner resolution fires the
        # extra profiling workspace allocation.
        dp_ep_owner = fused_config(2, True)
        dp_ep_legacy = fused_config(1, False)          # stale, wrong
        dp_ep_ambient = ambient_config(1, False)       # ambient, wrong

        ordinary_owner = fused_config(1, False)
        ordinary_legacy = fused_config(2, True)        # stale, wrong
        ordinary_ambient = ambient_config(2, True)     # ambient, wrong

        # Confirm the trap: active owner disagrees with both other sources.
        assert dp_ep_owner != dp_ep_legacy
        assert ordinary_owner != ordinary_legacy

        dp_ep_layer = layer(dp_ep_owner, dp_ep_ambient)
        ordinary_layer = layer(ordinary_owner, ordinary_ambient)

        dp_ep_kernel, dp_ep_experts = kernel_through_factory(
            dp_ep_layer, process_global=dp_ep_ambient, legacy_owner=dp_ep_legacy)
        ordinary_kernel, ordinary_experts = kernel_through_factory(
            ordinary_layer, process_global=ordinary_ambient, legacy_owner=ordinary_legacy)

        dp_ep_calls = []
        ordinary_calls = []
        dp_ep_out = run_cuda(dp_ep_kernel, inputs, profile=True, workspace=dp_ep_calls)
        ordinary_out = run_cuda(ordinary_kernel, inputs, profile=True, workspace=ordinary_calls)

        worst_case_bytes = 16384 * TOP_K * max(2 * INTERMEDIATE, HIDDEN) * 2
        assert workspace_bytes(dp_ep_calls) >= worst_case_bytes
        assert 0 < workspace_bytes(ordinary_calls) < worst_case_bytes
        assert workspace_bytes(ordinary_calls) > 0, ordinary_calls
        assert workspace_bytes(dp_ep_calls) > workspace_bytes(ordinary_calls), (dp_ep_calls, ordinary_calls)
        torch.testing.assert_close(dp_ep_out, baseline_out)
        torch.testing.assert_close(ordinary_out, baseline_out)
        stages["active_owner_workspace"] = {
            "dp_ep": workspace_bytes(dp_ep_calls), "ordinary": workspace_bytes(ordinary_calls),
        }
    except Exception as exc:  # noqa: BLE001 - report failing stage
        failures["challenge"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    print(json.dumps({"stages": stages, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_CONFIG_OWNERSHIP=FAIL")
        sys.exit(1)
    print("CHALLENGE_CONFIG_OWNERSHIP=PASS")


if __name__ == "__main__":
    main()
