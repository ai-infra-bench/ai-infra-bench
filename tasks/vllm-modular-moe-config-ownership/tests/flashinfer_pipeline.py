"""Real factory -> prepare -> expert apply -> finalize, on CUDA tensors.

Only collective transport and the external FlashInfer arithmetic call are
substituted. Transport preserves rank order, unequal sizes and tensor values.
The arithmetic boundary echoes its input; real single-rank Triton arithmetic
is checked independently by the main verifier. No constructor/storage field
is inspected and no prepare, selector, expert method or modular method is
replaced.
"""
from types import SimpleNamespace
from unittest.mock import patch

import torch
import vllm.model_executor.layers.quantization.utils.flashinfer_utils as factory
import vllm.model_executor.layers.fused_moe.flashinfer_cutlass_prepare_finalize as transport
import vllm.model_executor.layers.fused_moe.flashinfer_cutlass_moe as backend
from vllm.config import ParallelConfig, VllmConfig, set_current_vllm_config
from vllm.model_executor.layers.fused_moe.config import (
    FusedMoEConfig, FusedMoEParallelConfig, FUSED_MOE_UNQUANTIZED_CONFIG,
)


def to_list(tensor):
    return tensor.detach().cpu().tolist()


def exercise(cases):
    results = []
    for case in cases:
        owner = FusedMoEParallelConfig(**case['owner'])
        stale_owner = FusedMoEParallelConfig(**case['stale'])
        def config(parallel):
            return FusedMoEConfig(
                num_experts=case['global_experts'], experts_per_token=2,
                hidden_dim=case['hidden'],
                num_local_experts=case['global_experts'] // parallel.ep_size,
                moe_parallel_config=parallel, in_dtype=torch.bfloat16,
                max_num_tokens=16384,
            )
        active, stale = config(owner), config(stale_owner)
        ranks = [{key: torch.tensor(value, device='cuda', dtype=(
                    torch.long if key == 'ids' else torch.float32 if key == 'weights' else torch.bfloat16))
                  for key, value in rank.items()} for rank in case['ranks']]
        local = ranks[owner.dp_rank]
        events = []

        class Transport:
            def all_gatherv(self, tensors, dim, sizes):
                assert dim == 0 and list(sizes) == case['sizes']
                assert len(tensors) == 3
                for actual, key in zip(tensors, ('weights', 'ids', 'x')):
                    torch.testing.assert_close(actual, local[key], rtol=0, atol=0)
                gathered = [torch.cat([rank[key] for rank in ranks]) for key in ('weights', 'ids', 'x')]
                events.append({'kind': 'gather', 'sizes': list(sizes),
                               'sent': [to_list(t) for t in tensors],
                               'received': [to_list(t) for t in gathered]})
                return gathered

            def reduce_scatterv(self, tensor, dim, sizes):
                assert dim == 0 and list(sizes) == case['sizes']
                assert tensor.shape[0] == sum(sizes)
                start = sum(sizes[:owner.dp_rank])
                # Each virtual rank contributes the same identity-expert output.
                result = tensor[start:start + sizes[owner.dp_rank]] * len(ranks)
                events.append({'kind': 'reduce_scatter', 'sizes': list(sizes),
                               'input': to_list(tensor), 'output': to_list(result)})
                return result

        def arithmetic(**kwargs):
            # Observe the external kernel ABI, not an implementation's fields.
            events.append({'kind': 'expert', 'input': to_list(kwargs['input']),
                           'ids': to_list(kwargs['token_selected_experts']),
                           'weights': to_list(kwargs['token_final_scales']),
                           'parallel': {key: kwargs[key] for key in ('ep_size', 'ep_rank', 'tp_size', 'tp_rank')}})
            kwargs['output'].copy_(kwargs['input'])
            return kwargs['output']

        layer = SimpleNamespace(
            moe_config=active, moe_parallel_config=owner,
            vllm_config=SimpleNamespace(parallel_config=ParallelConfig(
                data_parallel_size=stale_owner.dp_size, enable_expert_parallel=stale_owner.use_ep)),
            quant_method=SimpleNamespace(get_fused_moe_quant_config=lambda _: FUSED_MOE_UNQUANTIZED_CONFIG),
            w13_weight=torch.zeros((active.num_local_experts, 2 * case['intermediate'], case['hidden']),
                                   device='cuda', dtype=torch.bfloat16),
            w2_weight=torch.zeros((active.num_local_experts, case['hidden'], case['intermediate']),
                                  device='cuda', dtype=torch.bfloat16),
        )
        with patch.object(transport, 'get_dp_group', return_value=Transport()), \
             patch.object(transport, 'get_local_sizes', return_value=case['sizes']), \
             patch.object(backend, 'flashinfer_cutlass_fused_moe', side_effect=arithmetic), \
             set_current_vllm_config(VllmConfig(parallel_config=layer.vllm_config.parallel_config)):
            output = factory.flashinfer_cutlass_moe_fp8(
                local['x'], layer, local['weights'], local['ids'],
                global_num_experts=case['global_experts'],
                use_deepseek_fp8_block_scale=True,
                moe=stale if case['explicit'] else None,
            )
        torch.cuda.synchronize()
        results.append({'events': events, 'output': to_list(output), 'device': output.device.type})
    return results
