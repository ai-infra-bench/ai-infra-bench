#!/usr/bin/env python3
"""Independent BMM challenge: fresh geometry, strided buffers, empty dimensions,
invalid cardinality and launch scaling. Base is deterministic already; its
failure must be per-item launches or the explicit input-validation contract.
"""
from __future__ import annotations

import json
import sys
import traceback

import torch

from vllm.model_executor.layers.batch_invariant import bmm_batch_invariant


# Fresh (dtype, batch, m, n, k) tuples; none appear in verify_bmm.correctness().
FRESH_CASES = [
    (torch.float16, 7, 24, 28, 36),
    (torch.float16, 11, 40, 16, 52),
    (torch.bfloat16, 6, 48, 32, 64),
    (torch.bfloat16, 13, 20, 44, 28),
    (torch.float32, 9, 36, 20, 48),
    (torch.float32, 3, 50, 50, 50),
]


def run_case(dtype, batch, m, n, k, seed) -> dict:
    torch.manual_seed(seed)
    a = torch.randn(batch, m, k, device="cuda", dtype=dtype)
    b = torch.randn(batch, k, n, device="cuda", dtype=dtype)

    batched = bmm_batch_invariant(a, b)
    looped = torch.cat(
        [bmm_batch_invariant(a[i : i + 1], b[i : i + 1]) for i in range(batch)]
    )
    # Bitwise, not approximate: the whole point of batch invariance.
    assert torch.equal(batched, looped), (
        dtype, batch, m, n, k, (batched - looped).abs().max().item()
    )

    # A mid-batch single-row slice must equal the corresponding batched row.
    mid = batch // 2
    single = bmm_batch_invariant(a[mid : mid + 1], b[mid : mid + 1])
    assert torch.equal(single[0], batched[mid])

    # Caller-owned destination identity and copy conversion on fresh shapes.
    out = torch.empty_like(batched)
    returned = bmm_batch_invariant(a, b, out=out)
    assert returned is out
    assert torch.equal(out, batched)
    torch.testing.assert_close(batched, torch.bmm(a,b), rtol=0.02, atol=0.02)
    for device, target_dtype, shape in [
        ('cpu', dtype, batched.shape),
        ('cuda', torch.float32 if dtype != torch.float32 else torch.float16, batched.shape),
        ('cuda', dtype, (1, *batched.shape)),
    ]:
        destination = torch.empty(shape, device=device, dtype=target_dtype)
        result = bmm_batch_invariant(a, b, out=destination)
        expected = torch.empty_like(destination).copy_(batched)
        assert result is destination and torch.equal(destination, expected)
    return {"dtype": str(dtype), "shape": [batch, m, n, k], "bitwise_invariant": True}


def edge_cases():
    from torch.profiler import profile, ProfilerActivity
    for batch,m,n,k in [(0,3,5,7),(2,0,5,7),(2,3,0,7),(2,3,5,0),(1,1,1,1)]:
        a=torch.randn(batch,m,k,device="cuda",dtype=torch.float16)
        b=torch.randn(batch,k,n,device="cuda",dtype=torch.float16)
        out=bmm_batch_invariant(a,b)
        torch.testing.assert_close(out,torch.bmm(a,b),rtol=0.02,atol=0.02)
    a=torch.randn(5,22,38,device="cuda",dtype=torch.float16)[:,::2,::2]
    b=torch.randn(5,26,38,device="cuda",dtype=torch.float16)[:,::2,::2].transpose(1,2)
    out=torch.empty(5,13,11,device="cuda",dtype=a.dtype).transpose(1,2)
    returned=bmm_batch_invariant(a,b,out=out)
    assert returned is out
    torch.testing.assert_close(out,torch.bmm(a,b),rtol=0.02,atol=0.02)
    for wrong in [b[:1], b[:3], b.cpu()]:
        try: bmm_batch_invariant(a,wrong)
        except (ValueError,RuntimeError,AssertionError,TypeError,IndexError): pass
        else: raise AssertionError('invalid operand silently accepted')
    bmm_batch_invariant(a,b);torch.cuda.synchronize()
    with profile(activities=[ProfilerActivity.CPU,ProfilerActivity.CUDA]) as prof:
        bmm_batch_invariant(a,b);torch.cuda.synchronize()
    kernels=[e.name for e in prof.events() if str(e.device_type).endswith('CUDA')]
    assert 0<len(kernels)<5, kernels
    return {"empty_and_strided":True,"kernel_count":len(kernels)}


def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    results = []
    failures = []
    try: results.append(edge_cases())
    except Exception: failures.append({"edge_cases": traceback.format_exc()})
    for idx, (dtype, batch, m, n, k) in enumerate(FRESH_CASES):
        try:
            results.append(run_case(dtype, batch, m, n, k, seed=4242 + idx))
        except Exception as exc:  # noqa: BLE001 - report every case
            failures.append(
                {
                    "case": [str(dtype), batch, m, n, k],
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
    print(json.dumps({"results": results, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_BMM=FAIL")
        sys.exit(1)
    print("CHALLENGE_BMM=PASS")


if __name__ == "__main__":
    main()
