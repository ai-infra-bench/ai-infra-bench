"""Independent owner/lifecycle challenge: unequal three-rank payloads on CUDA.

This enters the real public helper and runs real prepare, expert apply and
finalize. Only transport and external FlashInfer arithmetic are substituted.
No verifier workload generator, observer or parent checker is imported.
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import torch
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.model_executor.layers.fused_moe.config import (
    FusedMoEConfig, FusedMoEParallelConfig, FUSED_MOE_UNQUANTIZED_CONFIG,
)
import vllm.model_executor.layers.quantization.utils.flashinfer_utils as helper
import vllm.model_executor.layers.fused_moe.flashinfer_cutlass_prepare_finalize as prepare
import vllm.model_executor.layers.fused_moe.flashinfer_cutlass_moe as expert


def make_config(dp, tp, rank, tp_rank, ep):
    size, index = dp * tp, rank * tp + tp_rank
    parallel = FusedMoEParallelConfig(
        dp_size=dp, dp_rank=rank, pcp_size=1, pcp_rank=0,
        tp_size=1 if ep else size, tp_rank=0 if ep else index,
        ep_size=size if ep else 1, ep_rank=index if ep else 0, use_ep=ep,
        all2all_backend="allgather_reducescatter",
    )
    return FusedMoEConfig(
        num_experts=12, experts_per_token=2, hidden_dim=256,
        num_local_experts=12 // parallel.ep_size, moe_parallel_config=parallel,
        in_dtype=torch.bfloat16, max_num_tokens=16384,
    )


def main():
    from vllm.v1.worker.workspace import init_workspace_manager
    init_workspace_manager(torch.device("cuda:0"))
    rows = []
    for dp, tp, rank, tp_rank, ep, explicit in [
        (3, 2, 2, 1, True, False), (3, 1, 1, 0, False, True),
        (1, 2, 0, 1, True, True), (1, 1, 0, 0, False, True),
    ]:
        config = make_config(dp, tp, rank, tp_rank, ep)
        owner = config.moe_parallel_config
        stale = make_config(1, 1, 0, 0, False) if dp > 1 else make_config(3, 1, 1, 0, True)
        sizes = [2, 4, 7][:dp]
        inputs = []
        for r, n in enumerate(sizes):
            x = ((torch.arange(n * 256, device='cuda').reshape(n, 256) % 17) - 8 + 2*r).to(torch.bfloat16) / 8
            ids = (torch.arange(n * 2, device='cuda').reshape(n, 2) + 3*r) % 12
            weights = torch.tensor([0.125, 0.875], device='cuda').repeat(n, 1)
            inputs.append((weights, ids, x))
        joined = [torch.cat([data[j] for data in inputs]) for j in range(3)]
        local = inputs[rank]
        seen = []

        class Group:
            def all_gatherv(self, values, dim, sizes):
                assert dim == 0 and sizes == [len(data[0]) for data in inputs]
                for value, expected in zip(values, local):
                    torch.testing.assert_close(value, expected, rtol=0, atol=0)
                seen.append('gather')
                return joined

            def reduce_scatterv(self, value, dim, sizes):
                assert dim == 0
                torch.testing.assert_close(value, joined[2] + 1, rtol=0, atol=0)
                start = sum(sizes[:rank])
                seen.append('reduce')
                return value[start:start+sizes[rank]] * dp

        def compute(**kwargs):
            expected = joined if dp > 1 else local
            for key, value in zip(('token_final_scales', 'token_selected_experts', 'input'), expected):
                torch.testing.assert_close(kwargs[key], value.to(kwargs[key].dtype), rtol=0, atol=0)
            actual = tuple(kwargs[k] for k in ('ep_size', 'ep_rank', 'tp_size', 'tp_rank'))
            assert actual == (owner.ep_size, owner.ep_rank, owner.tp_size, owner.tp_rank), actual
            seen.append('expert')
            kwargs['output'].copy_(kwargs['input'] + 1)
            return kwargs['output']

        layer = SimpleNamespace(
            moe_config=config, moe_parallel_config=owner,
            quant_method=SimpleNamespace(get_fused_moe_quant_config=lambda _: FUSED_MOE_UNQUANTIZED_CONFIG),
            w13_weight=torch.zeros((config.num_local_experts, 256, 256), device='cuda', dtype=torch.bfloat16),
            w2_weight=torch.zeros((config.num_local_experts, 256, 128), device='cuda', dtype=torch.bfloat16),
            vllm_config=SimpleNamespace(parallel_config=ParallelConfig(data_parallel_size=stale.moe_parallel_config.dp_size, enable_expert_parallel=stale.moe_parallel_config.use_ep)),
        )
        with patch.object(prepare, 'get_dp_group', return_value=Group()), patch.object(prepare, 'get_local_sizes', return_value=sizes), patch.object(expert, 'flashinfer_cutlass_fused_moe', side_effect=compute), set_current_vllm_config(VllmConfig(parallel_config=layer.vllm_config.parallel_config)):
            out = helper.flashinfer_cutlass_moe_fp8(local[2], layer, local[0], local[1], global_num_experts=12, use_deepseek_fp8_block_scale=True, moe=stale if explicit else None)
        torch.testing.assert_close(out, (local[2] + 1) * dp, rtol=0, atol=0)
        assert seen == (['gather', 'expert', 'reduce'] if dp > 1 else ['expert']), seen
        rows.append(dict(dp=dp, tp=tp, rank=rank, tp_rank=tp_rank, ep=ep, rows=out.shape[0], events=seen))
    print('INDEPENDENT_PIPELINE_PASS ' + json.dumps(rows), flush=True)


if __name__ == '__main__':
    main()
