"""GPU probe for PR #29999's real modular-MoE profile allocation path."""

import inspect
import io
import logging

import torch

import vllm.config.vllm as vllm_config_module
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.forward_context import set_forward_context
from vllm.model_executor.layers.fused_moe.config import FusedMoEQuantConfig
from vllm.model_executor.layers.fused_moe.fused_moe import TritonExperts
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


def make_kernel(parallel_config):
    kwargs = {}
    if "parallel_config" in inspect.signature(FusedMoEModularKernel).parameters:
        kwargs["parallel_config"] = parallel_config
    quant = FusedMoEQuantConfig.make(None)
    return FusedMoEModularKernel(
        MoEPrepareAndFinalizeNoEP(), TritonExperts(quant), **kwargs
    )


def run_real_cuda_forward(kernel, config):
    torch.manual_seed(7)
    device = torch.device("cuda")
    dtype = torch.float16
    tokens, hidden, intermediate, experts, topk = 4, 64, 128, 4, 2
    x = torch.randn(tokens, hidden, device=device, dtype=dtype)
    w1 = torch.randn(experts, 2 * intermediate, hidden, device=device, dtype=dtype)
    w2 = torch.randn(experts, hidden, intermediate, device=device, dtype=dtype)
    logits = torch.randn(tokens, experts, device=device, dtype=dtype)
    topk_weights, topk_ids = torch.topk(logits, topk, dim=-1)
    topk_weights = torch.softmax(topk_weights.float(), dim=-1).to(dtype)

    # attn_metadata=None is the real profile marker used by
    # FusedMoEModularKernel._allocate_buffers. The context contains a valid
    # vLLM config but deliberately does not install the process-global config,
    # matching the worker lifecycle reported in the PR.
    with set_forward_context(None, config):
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
    return float(out.float().norm().item())


def main():
    assert torch.cuda.is_available()
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
    kernel = make_kernel(config.parallel_config)
    with set_current_vllm_config(config):
        valid_norm = run_real_cuda_forward(kernel, config)
    valid_warned = WARNING in capture.text
    assert not valid_warned, capture.text

    # Reproduction: valid config is reachable through ForwardContext but the
    # global config has ended before profile allocation. Base emits the
    # spurious warning; a correct patch accepts/caches parallel_config at
    # construction and does not emit it.
    capture.buffer = io.StringIO()
    clear_current_config()
    kernel = make_kernel(config.parallel_config)
    profile_norm = run_real_cuda_forward(kernel, config)
    profile_warned = WARNING in capture.text

    # Control 2: direct access with genuinely no installed config must keep
    # warning, preventing a solution that globally suppresses the log.
    capture.buffer = io.StringIO()
    clear_current_config()
    assert vllm_config_module.get_current_vllm_config() is not None
    missing_warned = WARNING in capture.text
    assert missing_warned, capture.text

    source_has_fix_api = (
        "parallel_config" in inspect.signature(FusedMoEModularKernel).parameters
    )
    expected_profile_warned = not source_has_fix_api
    assert profile_warned == expected_profile_warned, capture.text

    print(f"cuda_device={torch.cuda.get_device_name(0)}")
    print(f"source_has_fix_api={source_has_fix_api}")
    print(f"valid_profile_warned={valid_warned} norm={valid_norm:.6f}")
    print(f"lifecycle_gap_profile_warned={profile_warned} norm={profile_norm:.6f}")
    print(f"genuine_missing_config_warned={missing_warned}")
    print("PROFILE_WARNING_PROBE=PASS")


if __name__ == "__main__":
    main()
