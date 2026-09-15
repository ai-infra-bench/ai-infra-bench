"""Verifier-owned operands, generated before candidate imports in another process."""
import json
import os

def load_workload():
    with open(os.environ["AIB_WORKLOAD"]) as stream:
        return json.load(stream)

def make_workload(seed, artifact_dir):
    import torch
    import numpy as np
    from pathlib import Path
    torch.set_num_threads(4)
    generator = torch.Generator(device="cpu").manual_seed(seed)
    def values(shape, dtype):
        return torch.randn(shape, generator=generator).to(dtype).float().tolist()
    cases = []
    for dtype, batch, m, n, k in [(torch.float16,1,17,19,23),
            (torch.float16,5,33,29,41),(torch.bfloat16,3,31,37,43),
            (torch.bfloat16,8,64,48,80),(torch.float32,2,15,21,27),
            (torch.float32,4,32,24,40),
            (torch.float32,2,37,41,2560),(torch.float32,3,53,47,1536)]:
        cases.append({"dtype": str(dtype), "shape": [batch,m,n,k],
                      "a": values((batch,m,k),dtype), "b": values((batch,k,n),dtype)})
    # Exact-zero/cancellation inputs exercise the bit pattern contract. Empty
    # dimensions and noncontiguous views preserve the existing tensor interface.
    for dtype, shape, pattern, layout in [
        (torch.float16, (3, 9, 7, 12), 'zero', 'contiguous'),
        (torch.bfloat16, (2, 11, 13, 18), 'zero', 'contiguous'),
        (torch.float32, (4, 7, 5, 16), 'zero', 'contiguous'),
        (torch.float32, (3, 5, 7, 16), 'cancel', 'contiguous'),
        (torch.float16, (2, 0, 7, 9), 'random', 'contiguous'),
        (torch.float16, (2, 5, 0, 9), 'random', 'contiguous'),
        (torch.float16, (2, 5, 7, 0), 'random', 'contiguous'),
        (torch.bfloat16, (5, 11, 13, 19), 'random', 'strided'),
    ]:
        batch, m, n, k = shape
        a = torch.randn(batch, m, k, generator=generator).to(dtype)
        b = torch.randn(batch, k, n, generator=generator).to(dtype)
        if pattern == 'zero':
            a.zero_()
        elif pattern == 'cancel':
            a[..., 1::2] = a[..., ::2]
            b[:, 1::2] = -b[:, ::2]
        cases.append({'dtype': str(dtype), 'shape': list(shape),
                      'a': a.float().tolist(), 'b': b.float().tolist(), 'layout': layout})
    for dtype, batch, extra in [(torch.float16, 1, 2), (torch.bfloat16, 3, 1),
                                (torch.float32, 2, 3)]:
        m, n, k = 13, 17, 29
        cases.append({'dtype': str(dtype), 'shape': [batch, m, n, k],
                      'rhs_batch': batch + extra,
                      'a': values((batch, m, k), dtype),
                      'b': values((batch + extra, k, n), dtype)})
    shapes = [[8,512,512,2560],[32,512,512,2560],[8,1280,1280,2560]]
    directory = Path(artifact_dir)
    directory.mkdir(mode=0o755, exist_ok=True)
    performance = []
    for index, (batch, m, n, k) in enumerate(shapes):
        case = {"shape": [batch, m, n, k], "dtype": "torch.bfloat16"}
        for name, shape in [("a", (batch, m, k)), ("b", (batch, k, n))]:
            operand = torch.randn(shape, generator=generator).bfloat16().float()
            path = directory / f"large-{index}-{name}.npy"
            np.save(path, operand.numpy(), allow_pickle=False)
            path.chmod(0o444)
            case[name + "_path"] = str(path)
        performance.append(case)
    return {"correctness": cases, "performance_shapes": shapes, "performance": performance}


LAUNCH_GROUPS = [('torch.float16', [32, 32, 64]),
                 ('torch.bfloat16', [33, 29, 41])]
