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
    tokens, hidden, intermediate, experts, topk = (19, 80, 144, 4, 2)
    dtype = torch.bfloat16
    cases = []
    for _ in range(1):
        x = values((tokens,hidden),dtype)
        w1 = values((experts,2*intermediate,hidden),dtype)
        w2 = values((experts,hidden,intermediate),dtype)
        logits = torch.randn((tokens,experts),generator=generator)
        weights, ids = torch.topk(logits,topk,dim=-1)
        weights = torch.softmax(weights,dim=-1)
        cases.append({"x":x,"w1":w1,"w2":w2,"weights":weights.float().tolist(),
                      "ids":ids.tolist(),"dtype":str(dtype)})
    return {"numerics":cases}
