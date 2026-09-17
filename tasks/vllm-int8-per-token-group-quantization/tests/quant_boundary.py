"""Small-value observations compared against the frozen executable baseline."""
import json
import math
import subprocess
import sys


def cases():
    pattern = [-1., -.5, 0., .5, 1., .2, 0., -.2]
    result = [dict(name=name, shape=shape, group=group, eps=eps,
                 values=[v * magnitude for v in pattern])
            for name, shape, group, eps, magnitude in [
                ("subnormal-64", [3, 128], 64, 1e-45, 1e-38),
                ("subnormal-128", [4, 256], 128, 1e-45, 7e-38),
                ("subnormal-80", [2, 160], 80, 1e-45, 2e-38),
                ("small-normal", [2, 3, 128], 64, 1e-40, 1e-35),
                ("zero-underflow", [3, 128], 64, 1e-45, 0.),
                ("epsilon-dominated", [2, 256], 128, 1e-36, 1e-38),
                ("empty-leading", [0, 128], 64, 1e-10, 1.),
                ("empty-columns", [3, 0], 64, 1e-10, 1.),
                ("empty-higher-rank", [0, 3, 256], 128, 1e-10, 1.),
            ]]
    # Legal inputs on both sides of a launch-resource boundary. Include a group
    # larger than the entire default shared-memory budget, not only many groups.
    for name, shape, group, dtype in [
        ("large-fp32-at-limit", [16, 768], 768, "float32"),
        ("large-fp32-over-limit", [16, 1024], 1024, "float32"),
        ("large-fp16-at-limit", [16, 1536], 1536, "float16"),
        ("large-bf16-over-limit", [16, 2048], 2048, "bfloat16"),
        ("single-large-fp32", [1, 16384], 16384, "float32"),
        ("single-large-fp16", [1, 32768], 32768, "float16"),
        ("unaligned-fp16", [2, 3, 33], 33, "float16"),
        ("unaligned-bf16", [2, 3, 33], 33, "bfloat16"),
        ("unaligned-fp32", [2, 3, 17], 17, "float32"),
    ]:
        result.append(dict(name=name, shape=shape, group=group, dtype=dtype,
                           eps=1e-10, values=[v * 7 for v in pattern]))
    return result


def observe(cases, quantize):
    import torch
    result = []
    for case in cases:
        x = torch.tensor(case["values"], device="cuda",
                         dtype=getattr(torch, case.get("dtype", "float32")))
        numel = math.prod(case["shape"])
        repeats = (numel + len(case["values"]) - 1) // len(case["values"])
        x = x.repeat(repeats)[:numel].reshape(case["shape"])
        health = {}
        try:
            q, s = quantize(x, case["group"], case["eps"])
            torch.cuda.synchronize()
            if x.numel() == 0:
                # An invalid zero-grid launch may surface only on later work.
                health["post_empty_sum"] = torch.ones(3, device=x.device).sum().item()
        except Exception as exc:
            raise RuntimeError(f"{case['name']}: {exc}") from exc
        result.append(dict(name=case["name"], q_shape=list(q.shape),
                           s_shape=list(s.shape), q=q.flatten().tolist(),
                           s=s.flatten().tolist(), q_dtype=str(q.dtype),
                           s_dtype=str(s.dtype), q_device=str(q.device),
                           s_device=str(s.device), **health))
    return result


def frozen_observations(inputs, frozen_dir):
    code = """
import sys,json
sys.path.insert(0, sys.argv[1])
from frozen_reference_loader import load_frozen_reference
sys.path.insert(0, sys.argv[2])
from quant_boundary import observe
print('BOUNDARY=' + json.dumps(observe(json.load(sys.stdin), load_frozen_reference().per_token_group_quant_int8)))
"""
    from pathlib import Path
    proc = subprocess.run([sys.executable, "-I", "-c", code, frozen_dir,
                           str(Path(__file__).resolve().parent)],
                          input=json.dumps(inputs), capture_output=True, text=True,
                          timeout=180, check=True)
    lines = [line[9:] for line in proc.stdout.splitlines() if line.startswith("BOUNDARY=")]
    if len(lines) != 1:
        raise ValueError("missing frozen boundary observations")
    return json.loads(lines[0])


def compare(observed, expected):
    if not isinstance(observed, list) or len(observed) != len(expected):
        return ["missing boundary observations"]
    errors = []
    for got, ref in zip(observed, expected):
        if not isinstance(got, dict):
            errors.append("malformed observation")
            continue
        label = ref["name"]
        if "post_empty_sum" in ref and got.get("post_empty_sum") != ref["post_empty_sum"]:
            errors.append(label + ": subsequent CUDA work failed")
        if any(got.get(k) != ref[k] for k in ("name", "q_shape", "s_shape", "q_dtype", "s_dtype", "q_device", "s_device")):
            errors.append(label + ": output metadata mismatch")
        q, s = got.get("q"), got.get("s")
        if (not isinstance(q, list) or len(q) != len(ref["q"])
                or any(type(a) is not int or abs(a-b) > 1 for a,b in zip(q, ref["q"]))):
            errors.append(label + ": quantized difference exceeds 1")
        # A normal absolute tolerance would silently accept zero subnormal scales.
        if (not isinstance(s, list) or len(s) != len(ref["s"])
                or any(type(a) not in (float, int) or not math.isfinite(a)
                       or abs(a-b) > max(abs(b)*2e-4, 1.401298464324817e-45)
                       for a,b in zip(s, ref["s"]))):
            errors.append(label + ": scale mismatch")
    return errors
