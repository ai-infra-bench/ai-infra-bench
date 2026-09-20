#!/usr/bin/env python3
import argparse
import statistics
import torch
from vllm.model_executor.layers.quantization.utils import int8_utils


def triton_quant(x, group_size):
    q = torch.empty_like(x, dtype=torch.int8)
    s = torch.empty(x.shape[:-1] + (x.shape[-1] // group_size,),
                    device=x.device, dtype=torch.float32)
    programs = x.numel() // group_size
    block = int8_utils.triton.next_power_of_2(group_size)
    int8_utils._per_token_group_quant_int8[(programs,)](
        x, q, s, group_size, group_size, 1e-10,
        int8_min=-128, int8_max=127, BLOCK=block,
        num_warps=min(max(block // 256, 1), 8), num_stages=1)
    return q, s


def cuda_quant(x, group_size):
    q = torch.empty_like(x, dtype=torch.int8)
    s = torch.empty(x.shape[:-1] + (x.shape[-1] // group_size,),
                    device=x.device, dtype=torch.float32)
    torch.ops._C.per_token_group_quant_int8(x, q, s, group_size, 1e-10,
                                            -128.0, 127.0)
    return q, s


def reference(x, group_size):
    g = x.float().reshape(-1, group_size)
    s = g.abs().amax(dim=1).clamp_min(1e-10) / 127.0
    q = torch.clamp(torch.round(g / s[:, None]), -128, 127).to(torch.int8)
    return q.reshape_as(x), s.reshape(x.shape[:-1] +
                                      (x.shape[-1] // group_size,))


def timed_ms(fn, warmup=40, repeats=400):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    samples = []
    for _ in range(5):
        begin, end = torch.cuda.Event(True), torch.cuda.Event(True)
        begin.record()
        for _ in range(repeats):
            fn()
        end.record()
        end.synchronize()
        samples.append(begin.elapsed_time(end) / repeats)
    return statistics.median(samples)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("base", "candidate"), required=True)
    args = parser.parse_args()
    assert torch.cuda.is_available()
    print("gpu", torch.cuda.get_device_name(0), "capability",
          torch.cuda.get_device_capability(0), "torch", torch.__version__,
          "cuda", torch.version.cuda)
    has_op = hasattr(torch.ops._C, "per_token_group_quant_int8")
    print("native_int8_op", has_op)
    assert has_op == (args.mode == "candidate")

    torch.manual_seed(21476)
    cases = [((32, 128), 64, torch.float16),
             ((64, 256), 128, torch.bfloat16),
             ((7, 512), 64, torch.float32)]
    for shape, group_size, dtype in cases:
        x = (torch.randn(shape, device="cuda", dtype=dtype) * 8).contiguous()
        tq, ts = triton_quant(x, group_size)
        rq, rs = reference(x, group_size)
        assert (tq.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
        assert torch.allclose(ts, rs, rtol=2e-4, atol=2e-5)
        if has_op:
            cq, cs = cuda_quant(x, group_size)
            q_delta = (cq.to(torch.int16) - tq.to(torch.int16)).abs().max().item()
            assert q_delta <= 1
            assert torch.allclose(cs, ts, rtol=2e-4, atol=2e-5)
            print("correct", shape, group_size, dtype, "q_max_delta", q_delta,
                  "scale_max_delta", (cs - ts).abs().max().item())
        else:
            print("base_triton_correct", shape, group_size, dtype)

    if has_op:
        for shape, group_size in [((32, 128), 64), ((64, 256), 128),
                                  ((16, 512), 64), ((256, 4096), 128)]:
            x = (torch.randn(shape, device="cuda", dtype=torch.bfloat16) * 8).contiguous()
            cuda_ms = timed_ms(lambda: cuda_quant(x, group_size))
            triton_ms = timed_ms(lambda: triton_quant(x, group_size))
            print("timing", shape, group_size, "cuda_ms", round(cuda_ms, 6),
                  "triton_ms", round(triton_ms, 6), "speedup",
                  round(triton_ms / cuda_ms, 3))


if __name__ == "__main__":
    main()
