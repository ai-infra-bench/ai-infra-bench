#!/usr/bin/env python3
"""Independent fresh challenge for modular-MoE profile config lifecycle.

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. It enters through the same production factory
path (FusedMoEModularMethod.make -> FusedMoEModularKernel profile forward) but
with a MoE shape and a DP/EP-vs-ambient disagreement chosen independently of
tests/verify_profile_warning.py (which uses tokens/hidden/intermediate =
4/64/128 and dp_size=2).

Independent invariants re-derived here:
  1. A real CUDA profile forward whose valid config is reachable only through
     ForwardContext (process-global config already torn down) must NOT emit the
     "Current vLLM config is not set." warning.
  2. Genuinely missing config must STILL warn (no blanket suppression).
  3. The DP+EP active layer must take the extra profile-workspace allocation
     branch that a non-DP layer does not, following the ACTIVE layer config and
     not the ambient/global one.

Expected outcomes are Oracle/alternative PASS and Base/wrong-owner FAIL.
Actual execution results are recorded separately in e2e-evidence.json.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import sys
import traceback
from types import SimpleNamespace

import torch

import vllm.config.vllm as vllm_config_module
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.config import FusedMoEQuantConfig
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
import vllm.model_executor.layers.fused_moe.fused_moe_modular_method as method_module
from vllm.model_executor.layers.fused_moe.modular_kernel import FusedMoEModularKernel
from vllm.model_executor.layers.fused_moe.prepare_finalize import MoEPrepareAndFinalizeNoEP

WARNING = "Current vLLM config is not set."

# Fresh MoE geometry, distinct from the verifier's 4/64/128/4/2.
TOKENS, HIDDEN, INTERMEDIATE, EXPERTS, TOPK = 6, 96, 160, 8, 3


class Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.buffer = io.StringIO()

    def emit(self, record):
        self.buffer.write(self.format(record) + "\n")

    @property
    def text(self):
        return self.buffer.getvalue()


def clear_current_config():
    vllm_config_module._current_vllm_config = None
    vllm_config_module.get_cached_compilation_config.cache_clear()


def make_kernel_through_factory(config, ambient=None):
    original_method = method_module.FusedMoEModularMethod
    quant = FusedMoEQuantConfig.make(None)

    # Construct the production quant method with its real configuration. Model
    # weight loading is outside this profile slice; the forward receives tensors.
    from vllm.model_executor.layers.fused_moe.config import (
        FusedMoEConfig, FusedMoEParallelConfig,
    )
    from vllm.model_executor.layers.fused_moe.unquantized_fused_moe_method import (
        UnquantizedFusedMoEMethod,
    )
    parallel = config.parallel_config
    dp = parallel.data_parallel_size
    ep = parallel.enable_expert_parallel and dp > 1
    owner = FusedMoEParallelConfig(
        tp_size=1 if ep else dp, tp_rank=0, pcp_size=1, pcp_rank=0,
        dp_size=dp, dp_rank=0, ep_size=dp if ep else 1, ep_rank=0,
        use_ep=ep, all2all_backend=parallel.all2all_backend,
    )
    moe = FusedMoEConfig(
        num_experts=EXPERTS, experts_per_token=TOPK,
        hidden_dim=HIDDEN, num_local_experts=EXPERTS,
        moe_parallel_config=owner, in_dtype=torch.float16,
    )
    # CustomOp dispatch initialization requires the normal model-init context.
    # It ends before the production factory/kernel lifecycle under test.
    with set_current_vllm_config(config):
        old_quant = UnquantizedFusedMoEMethod(moe)
    old_quant.moe_quant_config = quant
    layer = SimpleNamespace(
        vllm_config=config, moe_config=moe, moe_parallel_config=owner,
        quant_method=old_quant, shared_experts_stream=None,
    )
    method_module.FusedMoEModularMethod = lambda old, kernel: kernel
    try:
        context = (
            set_current_vllm_config(ambient) if ambient is not None
            else contextlib.nullcontext()
        )
        with context:
            kernel = original_method.make(layer, old_quant,
                                          MoEPrepareAndFinalizeNoEP(), None)
    finally:
        method_module.FusedMoEModularMethod = original_method
    assert isinstance(kernel, FusedMoEModularKernel)
    return kernel


def real_cuda_forward(kernel, config, workspace=None):
    torch.manual_seed(99001)
    device = torch.device("cuda")
    dtype = torch.float16
    x = torch.randn(TOKENS, HIDDEN, device=device, dtype=dtype)
    w1 = torch.randn(EXPERTS, 2 * INTERMEDIATE, HIDDEN, device=device, dtype=dtype)
    w2 = torch.randn(EXPERTS, HIDDEN, INTERMEDIATE, device=device, dtype=dtype)
    logits = torch.randn(TOKENS, EXPERTS, device=device, dtype=dtype)
    topk_weights, topk_ids = torch.topk(logits, TOPK, dim=-1)
    topk_weights = torch.softmax(topk_weights.float(), dim=-1).to(dtype)
    with set_forward_context(None, config), observe_workspace_bytes(workspace, (x, w1, w2, topk_weights, topk_ids)):  # attn_metadata=None -> profile marker
        out = kernel(x, w1, w2, topk_weights, topk_ids, activation="silu",
                     global_num_experts=EXPERTS)
    torch.cuda.synchronize()
    assert out.is_cuda and out.shape == x.shape and torch.isfinite(out).all()
    return float(out.float().norm().item())


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




def measure_workspace(kernel, config):
    observed = []
    real_cuda_forward(kernel, config, workspace=observed)
    assert observed, "CUDA workspace operations were not reached"
    return max(observed)






def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    dp_ep = VllmConfig(parallel_config=ParallelConfig(
        data_parallel_size=4, enable_expert_parallel=True))
    non_dp = VllmConfig(parallel_config=ParallelConfig(
        data_parallel_size=1, enable_expert_parallel=False))

    logger = logging.getLogger("vllm.config.vllm")
    capture = Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)

    failures = {}
    stages = {}
    try:
        # Lifecycle gap: valid config only via ForwardContext, global torn down.
        capture.buffer = io.StringIO()
        clear_current_config()
        kernel = make_kernel_through_factory(dp_ep)
        gap_norm = real_cuda_forward(kernel, dp_ep)
        gap_warned = WARNING in capture.text
        assert not gap_warned, f"spurious warning during lifecycle gap: {capture.text!r}"
        stages["lifecycle_gap"] = {"warned": gap_warned, "norm": gap_norm}

        # Genuine missing config must still warn.
        capture.buffer = io.StringIO()
        clear_current_config()
        assert vllm_config_module.get_current_vllm_config() is not None
        missing_warned = WARNING in capture.text
        assert missing_warned, "genuine missing-config warning was suppressed"
        stages["genuine_missing"] = {"warned": missing_warned}

        # Active-layer DP+EP resolution: disagree ambient vs layer both ways.
        clear_current_config()
        dp_kernel = make_kernel_through_factory(dp_ep, ambient=non_dp)
        dp_workspace_bytes = measure_workspace(dp_kernel, dp_ep)
        clear_current_config()
        non_dp_kernel = make_kernel_through_factory(non_dp, ambient=dp_ep)
        non_dp_workspace_bytes = measure_workspace(non_dp_kernel, non_dp)
        worst_case_bytes = 16384 * TOPK * max(2 * INTERMEDIATE, HIDDEN) * 2
        assert dp_workspace_bytes >= worst_case_bytes
        assert 0 < non_dp_workspace_bytes < worst_case_bytes
        assert dp_workspace_bytes > non_dp_workspace_bytes, (
            "profile allocation followed ambient config, not active layer",
            dp_workspace_bytes, non_dp_workspace_bytes,
        )
        stages["active_owner_workspace"] = {"dp_ep": dp_workspace_bytes, "non_dp": non_dp_workspace_bytes}
    except Exception as exc:  # noqa: BLE001 - report the failing stage
        failures["challenge"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    print(json.dumps({"stages": stages, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_PROFILE_LIFECYCLE=FAIL")
        sys.exit(1)
    print("CHALLENGE_PROFILE_LIFECYCLE=PASS")


if __name__ == "__main__":
    main()
