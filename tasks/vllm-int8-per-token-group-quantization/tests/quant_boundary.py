"""Small-value observations compared against the frozen executable baseline."""
import json
import math
import subprocess
import sys


def cases():
    pattern = [-1., -.5, 0., .5, 1., .2, 0., -.2]
    return [dict(name=name, shape=shape, group=group, eps=eps,
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


def observe(cases, quantize):
    import torch
    result = []
    for case in cases:
        x = torch.tensor(case["values"], device="cuda", dtype=torch.float32)
        x = x.repeat(math.prod(case["shape"]) // len(case["values"])).reshape(case["shape"])
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
