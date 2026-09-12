"""Behavioral GPU probe for modular-MoE config ownership and profiling."""

import contextlib
import io
import json
import logging
import os
from types import SimpleNamespace

import torch
from workload import load_workload

import vllm.config.vllm as vllm_config_module
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.config import FusedMoEQuantConfig
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
import vllm.model_executor.layers.fused_moe.fused_moe_modular_method as method_module
from vllm.model_executor.layers.fused_moe.modular_kernel import (
    FusedMoEModularKernel,
)
from vllm.model_executor.layers.fused_moe.prepare_finalize import (
    MoEPrepareAndFinalizeNoEP,
)

WARNING = "Current vLLM config is not set."


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
    """Build through the production layer factory, not a private constructor API."""

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
        num_experts=4, experts_per_token=2,
        hidden_dim=64, num_local_experts=4,
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
    context = (
        set_current_vllm_config(ambient)
        if ambient is not None
        else contextlib.nullcontext()
    )
    with context:
        method = original_method.make(
            layer, old_quant, MoEPrepareAndFinalizeNoEP(), None,
        )
    def forward(x, w1, w2, weights, ids, *, activation, global_num_experts):
        # We supply deterministic router outputs and loaded weights; the real
        # modular method owns dispatch and all access to its internal storage.
        layer.w13_weight, layer.w2_weight = w1, w2
        layer.zero_expert_num, layer.zero_expert_type = 0, None
        layer.select_experts = lambda *args, **kwargs: (weights, ids, None)
        router_logits = torch.zeros((len(x), global_num_experts), device=x.device, dtype=x.dtype)
        return method.apply(
            layer, x, router_logits, top_k=ids.shape[1], renormalize=False,
            activation=activation, global_num_experts=global_num_experts,
        )
    return forward


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




def run_profile_and_measure_workspace(kernel, config):
    observed = []
    norm = run_real_cuda_forward(kernel, config, workspace=observed)
    assert observed, "CUDA workspace operations were not reached"
    return norm, max(observed)






def run_real_cuda_forward(kernel, config, workspace=None):
    case = load_workload()['numerics'][len(numerical_observations)]
    dtype = torch.float16
    x, w1, w2, topk_weights = [torch.tensor(case[k],device='cuda',dtype=dtype)
                              for k in ('x','w1','w2','weights')]
    topk_ids = torch.tensor(case['ids'],device='cuda',dtype=torch.long)
    experts = len(w1)
    # Production apply may legitimately reuse x for its output. Keep an input
    # snapshot for the trusted parent's numerical comparison.
    recorded_x = x.clone()

    # attn_metadata=None is the real profile marker used by
    # FusedMoEModularKernel._allocate_buffers. The context contains a valid
    # vLLM config but deliberately does not install the process-global config,
    # matching the worker lifecycle reported in the PR.
    with set_forward_context(None, config), observe_workspace_bytes(workspace, (x, w1, w2, topk_weights, topk_ids)):
        out = kernel(
            x,
            w1,
            w2,
            topk_weights,
            topk_ids,
            activation="silu",
            global_num_experts=experts,
        )
    torch.cuda.synchronize()
    assert out.is_cuda and out.shape == x.shape and torch.isfinite(out).all()
    numerical_observations.append(serialize_moe((recorded_x, w1, w2, topk_weights, topk_ids), out))
    return float(out.float().norm().item())


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


def main():
    assert torch.cuda.is_available()
    stages = []
    config = VllmConfig(
        parallel_config=ParallelConfig(
            data_parallel_size=2,
            enable_expert_parallel=True,
        )
    )

    logger = logging.getLogger("vllm.config.vllm")
    capture = Capture()
    logger.addHandler(capture)
    logger.setLevel(logging.WARNING)

    # Control 1: valid config explicitly installed: real CUDA profile forward
    # must not warn.
    clear_current_config()
    kernel = make_kernel_through_factory(config)
    with set_current_vllm_config(config):
        valid_norm = run_real_cuda_forward(kernel, config)
    valid_warned = WARNING in capture.text
    assert not valid_warned, capture.text
    stages.append("valid_profile_no_warning")

    # Reproduction: valid config is reachable through ForwardContext but the
    # global config has ended before profile allocation. Base emits the
    # spurious warning; a correct patch accepts/caches parallel_config at
    # construction and does not emit it.
    capture.buffer = io.StringIO()
    clear_current_config()
    kernel = make_kernel_through_factory(config)
    profile_norm = run_real_cuda_forward(kernel, config)
    profile_warned = WARNING in capture.text

    # Control 2: direct access with genuinely no installed config must keep
    # warning, preventing a solution that globally suppresses the log.
    capture.buffer = io.StringIO()
    clear_current_config()
    assert vllm_config_module.get_current_vllm_config() is not None
    missing_warned = WARNING in capture.text
    assert missing_warned, capture.text
    stages.append("genuine_missing_config_warns")

    # The active layer and ambient process config deliberately disagree. The
    # DP+EP layer must take the extra profile-workspace branch, while the
    # non-DP layer must not. This observes downstream production behavior and
    # permits any equivalent internal config representation.
    non_dp = VllmConfig(
        parallel_config=ParallelConfig(
            data_parallel_size=1,
            enable_expert_parallel=False,
        )
    )
    clear_current_config()
    dp_kernel = make_kernel_through_factory(config, ambient=non_dp)
    dp_norm, dp_workspace_bytes = run_profile_and_measure_workspace(
        dp_kernel, config
    )
    clear_current_config()
    non_dp_kernel = make_kernel_through_factory(non_dp, ambient=config)
    non_dp_norm, non_dp_workspace_bytes = run_profile_and_measure_workspace(
        non_dp_kernel, non_dp
    )
    assert dp_workspace_bytes > non_dp_workspace_bytes, (
        "profile allocation followed ambient config instead of active layer",
        dp_workspace_bytes,
        non_dp_workspace_bytes,
    )
    stages.append("active_layer_owner_wins")
    assert not profile_warned, capture.text
    stages.append("lifecycle_gap_no_warning")
    assert missing_warned, "genuine missing-config warning was suppressed"

    print(f"cuda_device={torch.cuda.get_device_name(0)}")
    print("private_constructor_parameter_names_scored=false")
    print("factory_config_provenance=production_workspace_behavior")
    print(
        "conflicting_config_workspace_bytes="
        f"dp_ep:{dp_workspace_bytes},non_dp:{non_dp_workspace_bytes} "
        f"norms:{dp_norm:.6f},{non_dp_norm:.6f}"
    )
    print(f"valid_profile_warned={valid_warned} norm={valid_norm:.6f}")
    print(f"lifecycle_gap_profile_warned={profile_warned} norm={profile_norm:.6f}")
    print(f"genuine_missing_config_warned={missing_warned}")
    write_report(stages, {"valid_warnings": valid_warned, "gap_warnings": profile_warned, "missing_warnings": missing_warned, "dp_workspace_bytes": dp_workspace_bytes, "ordinary_workspace_bytes": non_dp_workspace_bytes, "numerics": numerical_observations})
    print("PROFILE_WARNING_OBSERVATIONS_COMPLETE")


if __name__ == "__main__":
    main()
