"""Correctness, bitwise invariance, out=, and A100-local BMM timing probe."""

import json
import os
import statistics
import sys
import traceback

import torch

from workload import load_workload

import legacy_bmm as batch_module
from vllm.model_executor.layers.batch_invariant import bmm_batch_invariant


def correctness():
    results = []
    for case in load_workload()['correctness']:
        dtype = getattr(torch, case['dtype'].split('.')[-1])
        batch, m, n, k = case['shape']
        a = torch.tensor(case['a'], device="cuda", dtype=dtype)
        b = torch.tensor(case['b'], device="cuda", dtype=dtype)
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
        assert returned is out, "out= must return the caller's tensor object"
        assert returned.data_ptr() == out.data_ptr()
        assert torch.equal(out, batched)

        copies = []
        destinations = [("cuda", target, False) for target in
                        (torch.float16, torch.bfloat16, torch.float32) if target != dtype]
        destinations += [("cpu", dtype, False), ("cuda", dtype, True)]
        for device, target_dtype, broadcast in destinations:
            shape = (1, *batched.shape) if broadcast else batched.shape
            destination = torch.empty(shape, device=device, dtype=target_dtype)
            result = bmm_batch_invariant(a, b, out=destination)
            expected = torch.empty_like(destination).copy_(batched)
            assert result is destination
            assert torch.equal(destination, expected)
            copies.append({"device": destination.device.type,
                           "dtype": str(destination.dtype),
                           "shape": list(destination.shape),
                           "identity": result is destination,
                           "values": destination.float().cpu().tolist()})

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
                "a": a.float().cpu().tolist(), "b": b.float().cpu().tolist(),
                "batched": batched.float().cpu().tolist(),
                "single": loop.float().cpu().tolist(), "out": out.float().cpu().tolist(),
                "out_ptr": out.data_ptr(), "returned_ptr": returned.data_ptr(),
                "out_identity": returned is out,
                "out_copies": copies,
                "device": batched.device.type,
            }
        )
    return results


def assert_raises(label, fn):
    try:
        fn()
    except (AssertionError, RuntimeError, TypeError, ValueError, IndexError) as exc:
        return {"case": label, "exception": type(exc).__name__}
    raise AssertionError(f"{label} did not reject invalid input")


def error_contracts():
    cuda = torch.device("cuda")
    a = torch.randn((2, 8, 16), device=cuda, dtype=torch.float16)
    b = torch.randn((2, 16, 12), device=cuda, dtype=torch.float16)
    return [
        assert_raises(
            "dtype_mismatch",
            lambda: bmm_batch_invariant(a, b.to(torch.bfloat16)),
        ),
        assert_raises(
            "shape_mismatch",
            lambda: bmm_batch_invariant(
                a,
                torch.randn((2, 15, 12), device=cuda, dtype=a.dtype),
            ),
        ),
        assert_raises(
            "batch_mismatch",
            lambda: bmm_batch_invariant(a, b[:1]),
        ),
        assert_raises(
            "device_mismatch",
            lambda: bmm_batch_invariant(a, b.cpu()),
        ),
        assert_raises(
            "out_shape_mismatch",
            lambda: bmm_batch_invariant(
                a, b, out=torch.empty((2, 8, 11), device=cuda, dtype=a.dtype)
            ),
        ),
        assert_raises(
            "lhs_rank_mismatch",
            lambda: bmm_batch_invariant(a[0], b),
        ),
        assert_raises(
            "rhs_rank_mismatch",
            lambda: bmm_batch_invariant(a, b[0]),
        ),
    ]


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


def paired_speedup(shape=(8, 512, 512, 2560), warmup=5, iters=20, rounds=5):
    batch, m, n, k = shape
    torch.manual_seed(29345)
    a = torch.randn(batch, m, k, device="cuda", dtype=torch.bfloat16)
    b = torch.randn(batch, k, n, device="cuda", dtype=torch.bfloat16)

    def candidate():
        return bmm_batch_invariant(a, b)

    def legacy():
        return torch.stack(
            [batch_module.matmul_persistent(a[i], b[i]) for i in range(batch)]
        )

    for fn in (candidate, legacy):
        for _ in range(warmup):
            fn()
        torch.cuda.synchronize()

    def measure(fn):
        samples = []
        for _ in range(rounds):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            for _ in range(iters):
                fn()
            end.record()
            end.synchronize()
            samples.append(start.elapsed_time(end) / iters)
        return samples

    candidate_samples = measure(candidate)
    legacy_samples = measure(legacy)
    candidate_ms = statistics.median(candidate_samples)
    legacy_ms = statistics.median(legacy_samples)
    return {
        "shape": list(shape),
        "candidate_ms": candidate_ms,
        "legacy_ms": legacy_ms,
        "speedup": legacy_ms / candidate_ms,
        "candidate_samples": candidate_samples, "legacy_samples": legacy_samples,
    }


def launch_scaling():
    from torch.profiler import profile, ProfilerActivity
    result = []
    for batch in (1, 7, 29):
        a = torch.randn(batch, 32, 64, device="cuda", dtype=torch.float16)
        b = torch.randn(batch, 64, 32, device="cuda", dtype=torch.float16)
        bmm_batch_invariant(a, b)
        torch.cuda.synchronize()
        with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
            bmm_batch_invariant(a, b)
            torch.cuda.synchronize()
        kernels = [e.name for e in prof.events() if str(e.device_type).endswith("CUDA")]
        result.append({"batch": batch, "kernels": kernels})
    return result


def main():
    assert torch.cuda.is_available()
    stages, failures = {}, {}
    for name, fn in [("correctness", correctness), ("error_contracts", error_contracts),
                     ("launch_scaling", launch_scaling),
                     ("performance", lambda: [paired_speedup(shape) for shape in
                      [(8,512,512,2560),(32,512,512,2560),(8,1280,1280,2560)]])]:
        try:
            stages[name] = fn()
        except Exception:
            failures[name] = traceback.format_exc()
    result = {"stages": stages, "failures": failures, "device": torch.cuda.get_device_name(0)}
    with open(os.environ["AIB_OBSERVATIONS"], "w") as handle:
        json.dump(result, handle)
    print(json.dumps({"failures": failures, "performance": stages.get("performance"),
                      "launch_scaling": stages.get("launch_scaling")}, indent=2))


if __name__ == "__main__":
    main()
