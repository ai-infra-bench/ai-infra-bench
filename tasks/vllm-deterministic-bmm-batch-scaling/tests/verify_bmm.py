"""Correctness, bitwise invariance, out=, and A100-local BMM timing probe."""

import json
import os
import statistics
import sys
import traceback
from pathlib import Path

import torch

from workload import load_workload, LAUNCH_GROUPS

import legacy_bmm as batch_module
from vllm.model_executor.layers.batch_invariant import bmm_batch_invariant


def bitwise_equal(left, right):
    return (left.dtype == right.dtype and left.shape == right.shape
            and torch.equal(left.view({2: torch.int16, 4: torch.int32}[left.element_size()]),
                            right.view({2: torch.int16, 4: torch.int32}[right.element_size()])))


def correctness():
    results = []
    for case in load_workload()['correctness']:
        dtype = getattr(torch, case['dtype'].split('.')[-1])
        batch, m, n, k = case['shape']
        a = torch.tensor(case['a'], device="cuda", dtype=dtype).reshape(batch, m, k)
        b = torch.tensor(case['b'], device="cuda", dtype=dtype).reshape(case.get('rhs_batch', batch), k, n)
        if case.get('layout') == 'strided':
            backing = torch.empty(batch, m, 2 * k, device='cuda', dtype=dtype)
            backing[..., ::2].copy_(a)
            a = backing[..., ::2]
            b = b.transpose(1, 2).contiguous().transpose(1, 2)
            assert not a.is_contiguous() and not b.is_contiguous()
        batched = bmm_batch_invariant(a, b)
        loop = torch.cat(
            [bmm_batch_invariant(a[i : i + 1], b[i : i + 1]) for i in range(batch)]
        )
        assert bitwise_equal(batched, loop), (
            dtype,
            batch,
            m,
            n,
            k,
            "batch/single bit patterns differ",
        )

        assert batched.shape == (batch, m, n) and batched.dtype == dtype
        out = torch.empty(batch, n, m, device='cuda', dtype=dtype).transpose(1, 2)
        returned = bmm_batch_invariant(a, b, out=out)
        assert returned is out, "out= must return the caller's tensor object"
        assert returned.data_ptr() == out.data_ptr()
        assert bitwise_equal(out, batched)

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
            assert bitwise_equal(destination, expected)
            copies.append({"device": destination.device.type,
                           "dtype": str(destination.dtype),
                           "shape": list(destination.shape),
                           "identity": result is destination,
                           "values": destination.float().cpu().tolist()})

        reference = torch.bmm(a, b[:batch])
        # Numerical accuracy and bitwise batch invariance are both required.
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
                "output_shape": list(batched.shape), "output_dtype": str(batched.dtype),
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
        assert_raises("empty_batch", lambda: bmm_batch_invariant(a[:0], b[:0])),
        assert_raises("empty_lhs_batch", lambda: bmm_batch_invariant(a[:0], b)),
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


def paired_speedup(index, case, warmup=5, iters=20, rounds=5):
    import numpy as np
    shape = case['shape']
    batch, m, n, k = shape
    a, b = [torch.from_numpy(np.load(case[key + '_path'], allow_pickle=False))
            .to(device='cuda', dtype=torch.bfloat16) for key in ('a', 'b')]

    def candidate():
        return bmm_batch_invariant(a, b)

    def legacy():
        return torch.stack(
            [batch_module.matmul_persistent(a[i], b[i]) for i in range(batch)]
        )

    # Validate the same operands and shape that are timed. All snapshots and
    # batch/single comparisons are outside the CUDA-event measurement interval.
    before = candidate().clone()
    single = torch.cat([bmm_batch_invariant(a[i:i+1], b[i:i+1]) for i in range(batch)])
    output_dir = Path(os.environ['AIB_OBSERVATIONS']).parent
    for name, value in [('before', before), ('single', single)]:
        assert value.shape == (batch, m, n) and value.device == a.device
        assert value.dtype == a.dtype
        np.save(output_dir / f'large-{index}-{name}.npy', value.float().cpu().numpy(), allow_pickle=False)

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
    after = candidate()
    assert after.shape == (batch, m, n) and after.device == a.device and after.dtype == a.dtype
    np.save(output_dir / f'large-{index}-after.npy', after.float().cpu().numpy(), allow_pickle=False)
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
    for dtype_name, shape in LAUNCH_GROUPS:
        m, n, k = shape
        dtype = getattr(torch, dtype_name.split('.')[-1])
        for batch in (1, 7, 29):
            a = torch.randn(batch, m, k, device="cuda", dtype=dtype)
            b = torch.randn(batch, k, n, device="cuda", dtype=dtype)
            bmm_batch_invariant(a, b)
            torch.cuda.synchronize()
            with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
                bmm_batch_invariant(a, b)
                torch.cuda.synchronize()
            kernels = [e.name for e in prof.events() if str(e.device_type).endswith("CUDA")]
            result.append({"dtype": dtype_name, "shape": shape, "batch": batch, "kernels": kernels})
    return result


def main():
    assert torch.cuda.is_available()
    stages, failures = {}, {}
    for name, fn in [("correctness", correctness), ("error_contracts", error_contracts),
                     ("launch_scaling", launch_scaling),
                     ("performance", lambda: [paired_speedup(index, case) for index, case in
                      enumerate(load_workload()['performance'])])]:
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
