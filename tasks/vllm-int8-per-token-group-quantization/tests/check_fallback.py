"""Fresh-process public fallback check, independent of candidate local names.

Change the stable platform capability before importing the candidate module.
Keep the real CUDA Triton backend: this checks dispatch, not AMD code generation.
"""
import json
import torch
from triton.runtime.jit import JITFunction
import vllm.platforms as platforms


def main():
    platforms.current_platform.is_cuda = lambda: False
    from vllm.model_executor.layers.quantization.utils import int8_utils

    launches = []
    original_run = JITFunction.run

    def observe_run(kernel, *args, **kwargs):
        launches.append(type(kernel).__name__)
        return original_run(kernel, *args, **kwargs)

    JITFunction.run = observe_run
    try:
        torch.manual_seed(70126)
        for dtype in (torch.float16, torch.bfloat16, torch.float32):
            x = torch.randn((3, 192), device="cuda", dtype=dtype)
            with torch.profiler.profile(
                activities=[torch.profiler.ProfilerActivity.CPU]
            ) as prof:
                q, s = int8_utils.per_token_group_quant_int8(x, 64)
            assert not any(e.key == "_C::per_token_group_quant_int8"
                           for e in prof.key_averages())
            g = x.float().reshape(-1, 64)
            rs = g.abs().amax(dim=1).clamp_min(1e-10) / 127
            rq = (g / rs[:, None]).round().clamp(-128, 127).to(torch.int8)
            assert q.dtype == torch.int8 and q.shape == x.shape and q.device == x.device
            assert s.dtype == torch.float32 and s.shape == (3, 3) and s.device == x.device
            assert (q.short() - rq.reshape_as(q).short()).abs().max().item() <= 1
            assert torch.allclose(s, rs.reshape_as(s), rtol=2e-4, atol=2e-5)
        assert len(launches) >= 3, "fallback did not execute Triton"
    finally:
        JITFunction.run = original_run
    print("FALLBACK=" + json.dumps({"cases": 3, "triton": True, "native": False}))


if __name__ == "__main__":
    main()
