#!/usr/bin/env python3
"""Behavioral ownership contract for modular fused-MoE configuration."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, "/workspace/repo")

import torch
from workload import load_workload

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
from vllm.model_executor.layers.fused_moe.prepare_finalize import (
    MoEPrepareAndFinalizeNoEP,
)
from vllm.model_executor.layers.fused_moe.modular_kernel import (
    FusedMoEModularKernel,
)
from vllm.v1.worker.workspace import init_workspace_manager


EXPERTS = 4
TOKENS = 19
HIDDEN = 80
INTERMEDIATE = 144
TOP_K = 2


def fused_config(dp_size: int, use_ep: bool) -> FusedMoEParallelConfig:
    return FusedMoEParallelConfig(
        tp_size=1,
        pcp_size=1,
        dp_size=dp_size,
        ep_size=dp_size if use_ep else 1,
        tp_rank=0,
        pcp_rank=0,
        dp_rank=0,
        ep_rank=0,
        use_ep=use_ep,
        all2all_backend="allgather_reducescatter",
    )


def ambient_config(dp_size: int, use_ep: bool) -> ParallelConfig:
    return ParallelConfig(
        data_parallel_size=dp_size,
        enable_expert_parallel=use_ep,
    )


def make_components():
    # Use production Standard-format modular components whose experts advertise
    # supports_chunking() == True. This is required for the DP+EP-only
    # profiling workspace path in FusedMoEModularKernel to be reachable: that
    # branch is gated on (is_profile_run and supports_chunking() and
    # is_dp_ep). With a non-chunking expert the branch can never fire, so
    # is_dp_ep would have no observable effect and the ownership contract would
    # be untestable.
    return (
        MoEPrepareAndFinalizeNoEP(),
        TritonExperts(FUSED_MOE_UNQUANTIZED_CONFIG),
    )


def compatibility_kernel():
    return FusedMoEModularKernel(*make_components())


def layer_moe_config(owner):
    """Reproduce the configuration object and alias established by FusedMoE."""
    return FusedMoEConfig(
        num_experts=EXPERTS,
        experts_per_token=TOP_K,
        hidden_dim=HIDDEN,
        num_local_experts=EXPERTS,
        moe_parallel_config=owner,
        in_dtype=torch.bfloat16,
        max_num_tokens=16384,
    )


def layer(owner, ambient):
    return SimpleNamespace(
        moe_config=layer_moe_config(owner),
        moe_parallel_config=owner,
        vllm_config=SimpleNamespace(parallel_config=ambient),
        shared_experts_stream=None,
    )


def kernel_through_factory(moe_layer, process_global, legacy_owner):
    original_method = method_module.FusedMoEModularMethod
    prepare, experts = make_components()

    class ExistingQuantMethod:
        # A stale, initially equal config is deliberately available through the
        # old quant-method ownership path. Production behavior must still use
        # the active layer owner.
        moe = SimpleNamespace(moe_parallel_config=legacy_owner,
                              dp_size=legacy_owner.dp_size, use_ep=legacy_owner.use_ep)

        @staticmethod
        def select_gemm_impl(prepare_finalize, active_layer):
            return experts

    method_module.FusedMoEModularMethod = lambda old, kernel: kernel
    try:
        with set_current_vllm_config(
            VllmConfig(parallel_config=process_global)
        ):
            kernel = original_method.make(
                moe_layer,
                ExistingQuantMethod(),
                prepare,
                None,
            )
    finally:
        method_module.FusedMoEModularMethod = original_method
    assert isinstance(kernel, FusedMoEModularKernel)
    return kernel, experts


def make_inputs():
    case = load_workload()['numerics'][0]
    x, w1, w2 = [torch.tensor(case[k],device='cuda',dtype=torch.bfloat16)
                 for k in ('x','w1','w2')]
    weights = torch.tensor(case['weights'],device='cuda',dtype=torch.float32)
    ids = torch.tensor(case['ids'],device='cuda',dtype=torch.long)
    return x, w1, w2, weights, ids


def run_cuda(kernel, inputs, *, profile=False, workspace=None):
    hidden_states, w1, w2, weights, ids = inputs
    context = (
        set_forward_context(None, VllmConfig())
        if profile
        else contextlib.nullcontext()
    )
    with observe_workspace_bytes(workspace, inputs), context:
        output = kernel(
            hidden_states=hidden_states,
            w1=w1,
            w2=w2,
            topk_weights=weights,
            topk_ids=ids,
            inplace=False,
            global_num_experts=EXPERTS,
        )
    torch.cuda.synchronize()
    assert output.is_cuda and output.shape == hidden_states.shape
    assert bool(torch.isfinite(output).all()) and output.abs().sum().item() > 0
    numerical_observations.append(serialize_moe(inputs, output))
    return output


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




def flashinfer_behavior(moe_layer, process_global):
    original_prepare = flashinfer_utils.build_flashinfer_fp8_cutlass_moe_prepare_finalize
    original_select = flashinfer_utils.select_cutlass_fp8_gemm_impl
    prepare, experts = make_components()
    calls = []
    inputs = make_inputs()
    x, w1, w2, weights, ids = inputs
    class QuantMethod:
        @staticmethod
        def get_fused_moe_quant_config(active_layer):
            return FUSED_MOE_UNQUANTIZED_CONFIG
    moe_layer.quant_method = QuantMethod()
    moe_layer.w13_weight, moe_layer.w2_weight = w1, w2
    flashinfer_utils.build_flashinfer_fp8_cutlass_moe_prepare_finalize = lambda **kw: prepare
    flashinfer_utils.select_cutlass_fp8_gemm_impl = lambda **kw: experts
    try:
        with observe_workspace_bytes(calls, inputs), set_current_vllm_config(VllmConfig(parallel_config=process_global)):
            with set_forward_context(None, VllmConfig()):
                result = flashinfer_utils.flashinfer_cutlass_moe_fp8(x, moe_layer, weights, ids)
        torch.cuda.synchronize()
        numerical_observations.append(serialize_moe(inputs, result))
    finally:
        flashinfer_utils.build_flashinfer_fp8_cutlass_moe_prepare_finalize = original_prepare
        flashinfer_utils.select_cutlass_fp8_gemm_impl = original_select
    return workspace_bytes(calls)


def lora_factory_behavior(owner):
    import vllm.lora.layers.fused_moe as lora
    prepare, experts = make_components()
    inputs = make_inputs()
    calls = []
    class Quant:
        moe_quant_config = FUSED_MOE_UNQUANTIZED_CONFIG
        def select_gemm_impl(self, prepare_finalize, active_layer):
            return experts
    base = SimpleNamespace(top_k=TOP_K, ensure_moe_quant_config_init=lambda: None,
                           quant_method=Quant(), shared_experts=None,
                           moe_config=layer_moe_config(owner),
                           moe_parallel_config=owner, shared_experts_stream=None)
    obj = SimpleNamespace(base_layer=base)
    original = lora.FusedMoEModularKernel
    class Constructed(Exception): pass
    def construct(*args, **kwargs):
        kernel = original(*args, **kwargs)
        run_cuda(kernel, inputs, profile=True, workspace=calls)
        raise Constructed()
    lora.FusedMoEModularKernel = construct
    try:
        try: lora.FusedMoEWithLoRA._inject_lora_into_fused_moe(obj)
        except Constructed: pass
        else: raise AssertionError("LoRA factory did not reach modular construction")
    finally:
        lora.FusedMoEModularKernel = original
    return workspace_bytes(calls)


def functional_behavior():
    import vllm.model_executor.layers.fused_moe.cutlass_moe as cutlass
    prepare, experts = make_components()
    calls = []
    inputs = make_inputs()
    x,w1,w2,weights,ids = inputs
    original = cutlass.CutlassExpertsFp8
    cutlass.CutlassExpertsFp8 = lambda **kw: experts
    try:
        with observe_workspace_bytes(calls, inputs), set_current_vllm_config(VllmConfig(parallel_config=ambient_config(3, True))):
            with set_forward_context(None, VllmConfig()):
                out = cutlass.cutlass_moe_fp8(x,w1,w2,weights,ids,
                      ab_strides1=None,ab_strides2=None,c_strides1=None,c_strides2=None,
                      quant_config=FUSED_MOE_UNQUANTIZED_CONFIG,global_num_experts=EXPERTS)
        torch.cuda.synchronize()
        numerical_observations.append(serialize_moe(inputs,out))
    finally:
        cutlass.CutlassExpertsFp8 = original
    return workspace_bytes(calls)


numerical_observations = []


def serialize_moe(inputs, output):
    x, w1, w2, weights, ids = inputs
    return {"x": x.float().cpu().tolist(), "w1": w1.float().cpu().tolist(),
            "w2": w2.float().cpu().tolist(), "weights": weights.float().cpu().tolist(),
            "ids": ids.cpu().tolist(), "output": output.float().cpu().tolist(),
            "dtype": str(x.dtype), "device": output.device.type}


def write_report(stages, observations):
    path = os.environ.get("AIB_OBSERVATIONS")
    if path:
        with open(path, "w") as handle:
            json.dump(observations, handle)


def main() -> None:
    assert torch.cuda.is_available()
    assert torch.cuda.get_device_capability(0) == (8, 0)
    stages = []
    init_workspace_manager(torch.device("cuda:0"))
    inputs = make_inputs()

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
        compatibility = compatibility_kernel()
        compatibility_output = run_cuda(compatibility, inputs)
    finally:
        logging.getLogger("vllm.config.vllm").removeHandler(handler)
    assert not any("Current vLLM config is not set" in msg for msg in warnings)
    stages.append("compatibility_no_warning")

    # Start with value-equal but identity-distinct configs. Mutate only the
    # active layer owner before production construction, leaving the old
    # quant-method copy stale. This tests provenance without inspecting kernel
    # storage or requiring post-kernel-construction dynamic reconfiguration.
    dp_ep_owner = fused_config(1, False)
    dp_ep_legacy = fused_config(1, False)
    ordinary_owner = fused_config(2, True)
    ordinary_legacy = fused_config(2, True)
    assert dp_ep_owner == dp_ep_legacy and dp_ep_owner is not dp_ep_legacy
    assert ordinary_owner == ordinary_legacy and ordinary_owner is not ordinary_legacy
    dp_ep_owner.dp_size = 2
    dp_ep_owner.ep_size = 2
    dp_ep_owner.use_ep = True
    ordinary_owner.dp_size = 1
    ordinary_owner.ep_size = 1
    ordinary_owner.use_ep = False
    dp_ep_layer = layer(dp_ep_owner, ambient_config(1, False))
    ordinary_layer = layer(ordinary_owner, ambient_config(2, True))

    dp_ep_kernel, dp_ep_experts = kernel_through_factory(
        dp_ep_layer,
        process_global=ambient_config(1, False),
        legacy_owner=dp_ep_legacy,
    )
    ordinary_kernel, ordinary_experts = kernel_through_factory(
        ordinary_layer,
        process_global=ambient_config(2, True),
        legacy_owner=ordinary_legacy,
    )
    dp_ep_calls = []
    ordinary_calls = []
    dp_ep_output = run_cuda(dp_ep_kernel, inputs, profile=True, workspace=dp_ep_calls)
    ordinary_output = run_cuda(ordinary_kernel, inputs, profile=True, workspace=ordinary_calls)

    # DP+EP profiling reserves worst-case workspace; ordinary profiling uses
    # only the actual token workload. Inspect real returned workspace tensors.
    # Repeated or coalesced shape queries do not affect this measurement.
    assert workspace_bytes(ordinary_calls) > 0, ordinary_calls
    assert workspace_bytes(dp_ep_calls) > workspace_bytes(ordinary_calls), (dp_ep_calls, ordinary_calls)
    stages.append("active_owner_workspace_provenance")
    torch.testing.assert_close(dp_ep_output, compatibility_output)
    torch.testing.assert_close(ordinary_output, compatibility_output)
    stages.append("numerical_path_unchanged")

    dp_ep_flashinfer = flashinfer_behavior(
        dp_ep_layer,
        process_global=ambient_config(1, False),
    )
    ordinary_flashinfer = flashinfer_behavior(
        ordinary_layer,
        process_global=ambient_config(2, True),
    )
    assert dp_ep_flashinfer > ordinary_flashinfer > 0
    stages.append("flashinfer_consumer_follows_owner")

    print(
        json.dumps(
            {
                "compatibility_norm": float(
                    compatibility_output.float().norm()
                ),
                "consumers": [
                    "FusedMoEModularMethod.make",
                    "FusedMoEModularKernel.profile",
                    "flashinfer_cutlass_moe_fp8",
                ],
                "cuda": True,
                "global_conflicts_ignored": True,
                "gpu": torch.cuda.get_device_name(0),
                "internal_storage_scored": False,
                "post_construction_config_mutation_required": False,
                "value_equal_identity_distinct_decoys": True,
                "active_owner_mutated_before_consumer_construction": True,
                "dp_ep_owner_workspace_bytes": workspace_bytes(dp_ep_calls),
                "dp_consumer_workspace_bytes": dp_ep_flashinfer,
                "ordinary_owner_workspace_bytes": workspace_bytes(ordinary_calls),
                "ordinary_consumer_workspace_bytes": ordinary_flashinfer,
            },
            sort_keys=True,
        )
    )
    lora_dp = lora_factory_behavior(dp_ep_owner)
    lora_ordinary = lora_factory_behavior(ordinary_owner)
    functional_calls = functional_behavior()
    from flashinfer_pipeline import exercise
    pipeline = exercise(load_workload()['flashinfer_pipeline'])
    write_report(stages, {"flashinfer_pipeline": pipeline, "lora_dp_workspace_bytes":lora_dp, "lora_ordinary_workspace_bytes":lora_ordinary, "functional_workspace_bytes":functional_calls, "dp_workspace_bytes": workspace_bytes(dp_ep_calls), "ordinary_workspace_bytes": workspace_bytes(ordinary_calls), "dp_consumer_workspace_bytes": dp_ep_flashinfer, "ordinary_consumer_workspace_bytes": ordinary_flashinfer, "warnings": warnings, "numerics": numerical_observations})
    print("FUSED_MOE_OWNERSHIP_OBSERVATIONS_COMPLETE")


if __name__ == "__main__":
    main()
