#!/usr/bin/env python3
"""Independent fresh challenge for INT8 per-token-group quantization.

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. It enters through the same production API
(vllm.model_executor.layers.quantization.utils.int8_utils) on group sizes and
tensor shapes derived independently of tests/verify_int8_quant.py.

Independent invariants re-derived here:
  1. The public wrapper per_token_group_quant_int8 must select the native CUDA
     operator on a CUDA tensor (observed through the public native operator profiler event).
  2. Its output must match a from-scratch reference to within one int8 ULP.
  3. torch.ops._C.per_token_group_quant_int8 must honour custom eps / int8
     min / max arguments on fresh ranges.

Phase D runs this on the built A100 image against Oracle and the semantically
different alternate-native-kernel.patch (both PASS) and against Base (must
FAIL: the required native operator is absent).
"""
from __future__ import annotations

import json
import sys
import traceback

import torch

from vllm.model_executor.layers.quantization.utils import int8_utils


def reference(x, group_size, eps=1e-10, int8_min=-128, int8_max=127):
    g = x.float().reshape(-1, group_size)
    s = g.abs().amax(dim=1).clamp_min(eps) / float(int8_max)
    q = torch.clamp(torch.round(g / s[:, None]), int8_min, int8_max).to(torch.int8)
    return q.reshape_as(x), s.reshape(x.shape[:-1] + (x.shape[-1] // group_size,))


def cuda_quant(x, group_size, eps=1e-10, int8_min=-128.0, int8_max=127.0):
    q = torch.empty_like(x, dtype=torch.int8)
    s = torch.empty(
        x.shape[:-1] + (x.shape[-1] // group_size,),
        device=x.device,
        dtype=torch.float32,
    )
    torch.ops._C.per_token_group_quant_int8(x, q, s, group_size, eps, int8_min, int8_max)
    return q, s


def challenge_dispatch_and_accuracy() -> dict:
    # Fresh shapes/group sizes: (6,192) gs=96 and a negative-heavy row; the
    # verifier uses (4,128) gs=64.
    cases = [
        (torch.randn((6, 192), device="cuda", dtype=torch.float16).contiguous(), 96),
        (
            torch.tensor(
                [[-7.0, -3.5, -0.25, 0.0, 2.0, 9.0] * 15],
                device="cuda",
                dtype=torch.float16,
            ).contiguous(),
            90,
        ),
    ]
    checked = 0
    for x, group_size in cases:
        with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU]) as profile:
            q, s = int8_utils.per_token_group_quant_int8(x, group_size)
        assert "_C::per_token_group_quant_int8" in {event.key for event in profile.key_averages()}
        rq, rs = reference(x, group_size)
        assert (q.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
        assert torch.allclose(s, rs, rtol=2e-4, atol=2e-5)
        checked += 1
    return {"cases": checked, "native_dispatch": True}


def challenge_custom_range() -> dict:
    # Fresh custom eps/min/max not used by the verifier's argument cases.
    cases = [
        (torch.randn((4, 128), device="cuda", dtype=torch.float32).contiguous(), 64, 5e-4, -100, 100),
        (torch.randn((2, 96), device="cuda", dtype=torch.float16).contiguous(), 48, 1e-5, -16, 15),
    ]
    for dtype in (torch.float16, torch.bfloat16, torch.float32):
        for lower, upper in [(0, 11), (5, 29), (11, 93)]:
            x = torch.tensor([-5., -2., -.5, 0., .75, 3.], device="cuda", dtype=dtype)
            cases.append((x.repeat(64).reshape(2, 192), 96, 2e-5, lower, upper))
    checked = 0
    for x, group_size, eps, lower, upper in cases:
        q, s = cuda_quant(x, group_size, eps, float(lower), float(upper))
        rq, rs = reference(x, group_size, eps, lower, upper)
        assert int(q.min()) >= lower and int(q.max()) <= upper
        assert (q.to(torch.int16) - rq.to(torch.int16)).abs().max().item() <= 1
        assert torch.allclose(s, rs, rtol=2e-4, atol=2e-5)
        checked += 1
    return {"cases": checked, "custom_range_honoured": True}



def challenge_tiny_fp32():
    # Independent values and non-power-of-two groups, separate frozen process.
    import subprocess
    from pathlib import Path
    frozen = str(Path("/task/tests/frozen-reference"))
    code = """
import sys,json,torch
sys.path.insert(0,sys.argv[1])
from frozen_reference_loader import load_frozen_reference
f=load_frozen_reference().per_token_group_quant_int8
result=[]
for group in (48,96,128):
 x=torch.tensor([-3e-38,-1e-38,0.,1e-38,2e-38,3e-38],device='cuda',dtype=torch.float32).repeat(group).reshape(3,2*group)
 q,s=f(x,group,1e-44)
 result.append([q.flatten().tolist(),s.flatten().tolist()])
print('FRESH='+json.dumps(result))
"""
    proc=subprocess.run([sys.executable,"-I","-c",code,frozen],capture_output=True,text=True,check=True)
    refs=json.loads(next(line[6:] for line in proc.stdout.splitlines() if line.startswith('FRESH=')))
    for group,(refq,refs_) in zip((48,96,128),refs):
        x=torch.tensor([-3e-38,-1e-38,0.,1e-38,2e-38,3e-38],device='cuda',dtype=torch.float32).repeat(group).reshape(3,2*group)
        for fn in (cuda_quant,int8_utils.per_token_group_quant_int8):
            q,s=fn(x,group,1e-44)
            assert max(abs(a-b) for a,b in zip(q.flatten().tolist(),refq)) <= 1
            assert all(abs(a-b) <= max(abs(b)*2e-4,1.401298464324817e-45) for a,b in zip(s.flatten().tolist(),refs_))
    return {"cases": 3, "paths": 2}



def challenge_empty_inputs():
    cases=[((0,192),96,torch.float16), ((2,0),64,torch.bfloat16),
           ((2,0,96),48,torch.float32)]
    for shape,group,dtype in cases:
        for quant in (cuda_quant,int8_utils.per_token_group_quant_int8):
            x=torch.empty(shape,device="cuda",dtype=dtype)
            q,s=quant(x,group)
            torch.cuda.synchronize()
            assert q.shape==x.shape and q.dtype==torch.int8 and q.is_cuda
            assert tuple(s.shape)==shape[:-1]+(shape[-1]//group,) and s.dtype==torch.float32 and s.is_cuda
            assert torch.ones(5,device="cuda").sum().item()==5.
    return {"shapes":len(cases),"paths":2}


def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    stages = {
        "dispatch_and_accuracy": challenge_dispatch_and_accuracy,
        "custom_range": challenge_custom_range,
        "tiny_fp32": challenge_tiny_fp32,
        "empty_inputs": challenge_empty_inputs,
    }
    passed = {}
    failures = {}
    for name, fn in stages.items():
        try:
            passed[name] = fn()
        except Exception as exc:  # noqa: BLE001 - report every stage
            failures[name] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
    print(json.dumps({"passed": passed, "failures": failures}, indent=2, sort_keys=True))
    if failures:
        print("CHALLENGE_INT8_QUANT=FAIL")
        sys.exit(1)
    print("CHALLENGE_INT8_QUANT=PASS")


if __name__ == "__main__":
    main()
