"""Verifier-owned operands, generated before candidate imports in another process."""
import json
import os

def load_workload():
    with open(os.environ["AIB_WORKLOAD"]) as stream:
        return json.load(stream)

def make_workload(seed):
    import torch
    generator = torch.Generator(device="cpu").manual_seed(seed)
    def values(shape, dtype):
        return torch.randn(shape, generator=generator).to(dtype).float().tolist()
    cases = []
    for dtype, batch, m, n, k in [(torch.float16,1,17,19,23),
            (torch.float16,5,33,29,41),(torch.bfloat16,3,31,37,43),
            (torch.bfloat16,8,64,48,80),(torch.float32,2,15,21,27),
            (torch.float32,4,32,24,40)]:
        cases.append({"dtype": str(dtype), "shape": [batch,m,n,k],
                      "a": values((batch,m,k),dtype), "b": values((batch,k,n),dtype)})
    return {"correctness": cases,
            "performance_shapes": [[8,512,512,2560],[32,512,512,2560],[8,1280,1280,2560]]}
