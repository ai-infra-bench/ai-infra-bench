"""Correctness, bitwise invariance, out=, and A100-local BMM timing probe."""

import json
import statistics
import sys

import torch

from vllm.model_executor.layers.batch_invariant import bmm_batch_invariant


def correctness():
    cases = [
        (torch.float16, 1, 17, 19, 23),
        (torch.float16, 5, 33, 29, 41),
        (torch.bfloat16, 3, 31, 37, 43),
        (torch.bfloat16, 8, 64, 48, 80),
        (torch.float32, 2, 15, 21, 27),
        (torch.float32, 4, 32, 24, 40),
    ]
    results = []
    for idx, (dtype, batch, m, n, k) in enumerate(cases):
        torch.manual_seed(100 + idx)
        a = torch.randn(batch, m, k, device="cuda", dtype=dtype)
        b = torch.randn(batch, k, n, device="cuda", dtype=dtype)
        batched = bmm_batch_invariant(a, b)
        loop = torch.cat(
            [bmm_batch_invariant(a[i : i + 1], b[i : i + 1]) for i in range(batch)]
        )
        assert torch.equal(batched, loop), (
            dtype,
            batch,
            m,
            n,
            k,
            (batched - loop).abs().max().item(),
        )

        out = torch.empty_like(batched)
        returned = bmm_batch_invariant(a, b, out=out)
        assert returned.data_ptr() == out.data_ptr()
        assert torch.equal(out, batched)

        reference = torch.bmm(a, b)
        # This deterministic Triton kernel uses a fixed reduction order that
        # differs from cuBLAS/TF32. Numerical closeness is a secondary sanity
        # check; bitwise batch-vs-single equality above remains the hard gate.
        tol = 2e-2
        torch.testing.assert_close(batched, reference, rtol=tol, atol=tol)
        results.append(
            {
                "dtype": str(dtype),
                "shape": [batch, m, n, k],
                "bitwise_invariant": True,
                "out_identity": True,
            }
        )
    return results


def timed_case(shape, warmup=5, iters=20, rounds=5):
    batch, m, n, k = shape
    torch.manual_seed(sum(shape))
    a = torch.randn(batch, m, k, device="cuda", dtype=torch.bfloat16)
    b = torch.randn(batch, k, n, device="cuda", dtype=torch.bfloat16)
    for _ in range(warmup):
        bmm_batch_invariant(a, b)
    torch.cuda.synchronize()
    samples = []
    for _ in range(rounds):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(iters):
            bmm_batch_invariant(a, b)
        end.record()
        torch.cuda.synchronize()
        samples.append(start.elapsed_time(end) / iters)
    return {"shape": list(shape), "median_ms": statistics.median(samples), "samples_ms": samples}


def main():
    assert torch.cuda.is_available()
    correctness_results = correctness()
    perf_shapes = [
        (8, 512, 512, 2560),
        (32, 512, 512, 2560),
        (8, 1280, 1280, 2560),
    ]
    report = {
        "device": torch.cuda.get_device_name(0),
        "implementation": sys.argv[1] if len(sys.argv) > 1 else "unknown",
        "correctness": correctness_results,
        "performance": [timed_case(shape) for shape in perf_shapes],
    }
    print(json.dumps(report, indent=2))
    print("BMM_PROBE=PASS")


if __name__ == "__main__":
    main()
