"""Curator-only probes; never installed in the agent image."""
import itertools
import json
import torch
from vllm.model_executor.layers.quantization.utils import int8_utils, fp8_utils


def native(x, group, eps, lower, upper):
    q = torch.empty_like(x, dtype=torch.int8)
    s = torch.empty(x.shape[:-1] + (x.shape[-1] // group,),
                    device=x.device, dtype=torch.float32)
    torch.ops._C.per_token_group_quant_int8(x, q, s, group, eps, lower, upper)
    return q, s


def check_int8():
    records = []
    torch.manual_seed(70918)
    for dtype, group in itertools.product(
        [torch.float16, torch.bfloat16, torch.float32],
        [3, 33, 769, 1009, 12289, 24577],
    ):
        x = torch.randn((2, 3, group), device="cuda", dtype=dtype) * 0.7
        for mode, eps, lower, upper in [
            ("public", 1e-10, -128, 127),
            ("native", 1e-10, -128, 127),
            ("native", 0.125, 7, 31),
        ]:
            q, s = (int8_utils.per_token_group_quant_int8(x, group)
                    if mode == "public" else native(x, group, eps, lower, upper))
            g = x.float().reshape(-1, group)
            expected_s = g.abs().amax(dim=1).clamp_min(eps) / upper
            expected_q = (g / expected_s[:, None]).round().clamp(lower, upper).to(torch.int8)
            delta = (q.short() - expected_q.reshape_as(q).short()).abs().max().item()
            assert delta <= 1, (dtype, group, mode, delta)
            torch.testing.assert_close(s.flatten(), expected_s, rtol=2e-4, atol=2e-5)
            records.append(dict(dtype=str(dtype), group=group, mode=mode,
                                eps=eps, lower=lower, upper=upper, max_delta=delta))
    return records


def check_fp8():
    records = []
    torch.manual_seed(420918)
    for shape, column, ue8m0, group in itertools.product(
        [(32, 128), (64, 256), (16, 512)], [False, True], [False, True], [64, 128]
    ):
        x = torch.randn(shape, device="cuda", dtype=torch.bfloat16) * 8
        q, s = fp8_utils.per_token_group_quant_fp8(
            x, group, column_major_scales=column, use_ue8m0=ue8m0)
        g = x.float().reshape(-1, group)
        expected_s = g.abs().amax(dim=1).clamp_min(1e-10) / 448
        if ue8m0:
            expected_s = torch.exp2(torch.ceil(torch.log2(expected_s.abs().clamp_min(1e-10))))
        expected_q = (g / expected_s[:, None]).clamp(-448, 448).to(torch.float8_e4m3fn)
        torch.testing.assert_close(q.float(), expected_q.reshape_as(q).float(), atol=0.15, rtol=0.15)
        torch.testing.assert_close(s, expected_s.reshape_as(s), atol=0.01, rtol=0.01)
        records.append(dict(shape=shape, column=column, ue8m0=ue8m0, group=group))
    return records


if __name__ == "__main__":
    import sys
    results = {"fp8": check_fp8()}
    if "--base" not in sys.argv:
        results["int8"] = check_int8()
    print("PROBE=" + json.dumps(results))
