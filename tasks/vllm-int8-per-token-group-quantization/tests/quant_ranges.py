"""Configured INT8 ranges checked against the pinned executable Triton kernel.

Only the declared native API takes custom bounds in the frozen public contract;
no new keyword arguments are required on the Python convenience wrapper.
"""
import json
import math
from pathlib import Path
import subprocess
import sys


def cases():
    result = []
    for dtype, group, eps in [("float16", 64, 1e-5),
                              ("bfloat16", 80, 1e-4),
                              ("float32", 128, 1e-10)]:
        for lower, upper in [(-128, 127), (-83, 71), (0, 127),
                             (1, 100), (50, 100), (3, 7)]:
            result.append(dict(name=f"{dtype}-{lower}-{upper}", dtype=dtype,
                               shape=[2, 3, group * 2], group=group, eps=eps,
                               lower=lower, upper=upper,
                               values=[-2., -1., 0., .25, .5, 1., 1.5, 2.]))
    return result


def observe(inputs, quantize):
    import torch
    result = []
    for case in inputs:
        x = torch.tensor(case['values'], device='cuda', dtype=getattr(torch, case['dtype']))
        x = x.repeat(math.prod(case['shape']) // x.numel()).reshape(case['shape'])
        try:
            q, s = quantize(x, case['group'], case['eps'], case['lower'], case['upper'])
            torch.cuda.synchronize()
        except Exception as exc:
            raise RuntimeError(f"{case['name']}: {exc}") from exc
        result.append(dict(name=case['name'], q_shape=list(q.shape), s_shape=list(s.shape),
                           q=q.flatten().tolist(), s=s.flatten().tolist(),
                           q_dtype=str(q.dtype), s_dtype=str(s.dtype),
                           q_device=str(q.device), s_device=str(s.device),
                           lower=case['lower'], upper=case['upper']))
    return result


def frozen_observations(inputs, frozen_dir):
    code = '''
import sys,json,torch,triton
sys.path.insert(0,sys.argv[1])
from frozen_reference_loader import load_frozen_reference
frozen=load_frozen_reference()
sys.path.insert(0,sys.argv[2])
from quant_ranges import observe
def quantize(x, group, eps, lower, upper):
    q=torch.empty_like(x,dtype=torch.int8)
    s=torch.empty(x.shape[:-1]+(x.shape[-1]//group,),device=x.device,dtype=torch.float32)
    block=triton.next_power_of_2(group)
    frozen._per_token_group_quant_int8[(x.numel()//group,)](
        x,q,s,group,group,eps,lower,upper,BLOCK=block,
        num_warps=min(max(block//256,1),8),num_stages=1)
    return q,s
print('RANGES='+json.dumps(observe(json.load(sys.stdin),quantize)))
'''
    proc = subprocess.run([sys.executable, '-I', '-c', code, frozen_dir,
                           str(Path(__file__).resolve().parent)], input=json.dumps(inputs),
                          capture_output=True, text=True, timeout=180, check=True)
    lines = [line[7:] for line in proc.stdout.splitlines() if line.startswith('RANGES=')]
    if len(lines) != 1:
        raise ValueError('missing frozen range observations')
    return json.loads(lines[0])


def compare(observed, expected):
    from quant_boundary import compare as compare_values
    errors = compare_values(observed, expected)
    if not isinstance(observed, list) or len(observed) != len(expected):
        return errors
    for got, ref in zip(observed, expected):
        if not isinstance(got, dict):
            continue
        if (got.get('lower'), got.get('upper')) != (ref['lower'], ref['upper']):
            errors.append(ref['name'] + ': wrong configured range')
        values = got.get('q')
        if isinstance(values, list) and any(type(v) is not int or not ref['lower'] <= v <= ref['upper'] for v in values):
            errors.append(ref['name'] + ': output outside configured range')
    return errors
