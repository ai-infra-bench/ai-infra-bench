#!/usr/bin/env python3
"""Independent curator challenge; not a scored test or agent-visible fixture."""
import json
import sys
import torch
sys.path.insert(0, '/workspace/repo')
from vllm.model_executor.models.utils import _merge_multimodal_embeddings as merge

results=[]
for device in ('cpu', 'cuda'):
    for count in (0, 1, 7):
        # A transposed destination probes stride handling, unlike the verifier's
        # contiguous destination. The source is a single 3-D tensor.
        x=torch.full((7, 17), -9., device='cuda', dtype=torch.float16).t()
        mask_cpu=torch.arange(17)<count
        mask=mask_cpu.to(device)
        values=torch.arange(count*7, dtype=torch.float32, device='cuda').reshape(1,count,7)
        result=merge(x,values,mask)
        expected=torch.full((17,7),-9.,dtype=torch.float16)
        expected[mask_cpu]=torch.arange(count*7,dtype=torch.float16).reshape(count,7)
        assert result is x and torch.equal(x.cpu(),expected)
        results.append(dict(device=device,count=count,passed=True))
print(json.dumps({'torch':torch.__version__,'cases':results}))
