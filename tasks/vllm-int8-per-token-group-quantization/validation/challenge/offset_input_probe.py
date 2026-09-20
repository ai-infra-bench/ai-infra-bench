"""Independent contiguous-view challenge; run each case in a fresh process."""
import argparse
import json
import torch
from vllm.model_executor.layers.quantization.utils.int8_utils import per_token_group_quant_int8

p = argparse.ArgumentParser()
p.add_argument('--dtype', choices=['float16', 'bfloat16', 'float32'], required=True)
p.add_argument('--offset', type=int, required=True)
p.add_argument('--mode', choices=['public', 'native'], default='public')
a = p.parse_args()
assert a.offset >= 0
torch.manual_seed(7071)
values = torch.randn((2, 3, 128), device='cuda', dtype=getattr(torch, a.dtype))
storage = torch.empty(values.numel() + a.offset, device='cuda', dtype=values.dtype)
view = storage[a.offset:]
view.copy_(values.flatten())
x = view.reshape_as(values)
assert x.is_contiguous() and x.storage_offset() == a.offset
case = dict(dtype=a.dtype, offset=a.offset, mode=a.mode, shape=list(x.shape),
            group=64, contiguous=x.is_contiguous(), pointer_mod16=x.data_ptr() % 16)
print('CASE=' + json.dumps(case), flush=True)
if a.mode == 'public':
    q, s = per_token_group_quant_int8(x, 64)
else:
    import sys
    sys.path.insert(0, '/tests')
    from native_interface import make_quantizer
    q, s = make_quantizer(torch.ops._C.per_token_group_quant_int8)(x, 64)

torch.cuda.synchronize()
g = values.float().reshape(-1, 64)
rs = g.abs().amax(1).clamp_min(1e-10) / 127
rq = (g / rs[:, None]).round().clamp(-128, 127).to(torch.int8)
assert q.dtype == torch.int8 and q.shape == values.shape
assert s.dtype == torch.float32 and s.shape == (2, 3, 2)
delta = (q.short() - rq.reshape_as(q).short()).abs().max().item()
assert delta <= 1, delta
torch.testing.assert_close(s.flatten(), rs, rtol=2e-4, atol=2e-5)
print('OFFSET_PASS=' + json.dumps(dict(case, max_q_delta=delta)), flush=True)
