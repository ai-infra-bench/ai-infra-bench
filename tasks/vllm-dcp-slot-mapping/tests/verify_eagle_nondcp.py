"""Non-DCP preservation through Eagle propose and real FlashInfer attention.

A deterministic draft model substitutes weights. The two-step eager draft runs
production input kernels, metadata planning and CUDA attention; its outputs are
checked against uniform-attention arithmetic, not an implementation's fields.
"""
import json
import pathlib
import sys
import tempfile
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, '/workspace/repo')
import torch
from vllm.config import (CacheConfig, CompilationConfig, ModelConfig,
                         ParallelConfig, SchedulerConfig, SpeculativeConfig, VllmConfig,
                         set_current_vllm_config)
from vllm.config.compilation import CUDAGraphMode
from vllm.forward_context import get_forward_context
from vllm.sampling_params import SamplingParams
from vllm.v1.core.sched.output import NewRequestData, SchedulerOutput
from vllm.v1.kv_cache_interface import FullAttentionSpec
from vllm.v1.core.kv_cache_utils import get_kv_cache_groups, get_kv_cache_config_from_groups
from vllm.v1.attention.backends import flashinfer
from vllm.model_executor.layers.attention.attention import Attention
from vllm.v1.worker.gpu.model_runner import GPUModelRunner
import vllm.distributed as distributed
import vllm.distributed.parallel_state as parallel_state
import vllm.v1.worker.gpu.block_table as table_module
import vllm.v1.worker.gpu.model_runner as runner_module
import vllm.v1.worker.gpu.cudagraph_utils as graph_module

GROUP = SimpleNamespace(world_size=1, rank_in_group=0)


def _run_case(lengths, steps=2):
    with tempfile.TemporaryDirectory(prefix='eagle-normal-') as directory:
        pathlib.Path(directory, 'config.json').write_text(json.dumps({
            'model_type': 'llama', 'architectures': ['LlamaForCausalLM'],
            'hidden_size': 512, 'intermediate_size': 1024, 'num_hidden_layers': 1,
            'num_attention_heads': 4, 'num_key_value_heads': 1, 'head_dim': 128,
            'vocab_size': 256, 'max_position_embeddings': 128,
        }))
        model_config = ModelConfig(model=directory, dtype='float16',
            max_model_len=128, skip_tokenizer_init=True, enforce_eager=True)
        parallel_config = ParallelConfig(tensor_parallel_size=1,
            decode_context_parallel_size=1, distributed_executor_backend='mp')
        speculative_config = SpeculativeConfig(model=directory, method='eagle',
            num_speculative_tokens=steps, target_model_config=model_config,
            target_parallel_config=parallel_config)
        cfg = VllmConfig(
            model_config=model_config,
            speculative_config=speculative_config,
            cache_config=CacheConfig(block_size=16, cache_dtype='auto'),
            parallel_config=parallel_config,
            scheduler_config=SchedulerConfig(max_num_batched_tokens=128,
                max_num_seqs=2, max_model_len=128, async_scheduling=False,
                is_encoder_decoder=False),
            compilation_config=CompilationConfig(mode=0, cudagraph_mode=CUDAGraphMode.NONE),
        )
        cfg.attention_config.use_trtllm_attention = False
        layer = 'model.layers.0.self_attn.attn'
        with set_current_vllm_config(cfg):
            attention_layer = Attention(num_heads=4, head_size=128, scale=128**-0.5,
                      num_kv_heads=1, cache_config=cfg.cache_config,
                      prefix=layer, attn_backend=flashinfer.FlashInferBackend)
            kvspec = FullAttentionSpec(block_size=16, num_kv_heads=1,
                                      head_size=128, dtype=torch.float16)
            groups = get_kv_cache_groups(cfg, {layer: kvspec})
            kvconfig = get_kv_cache_config_from_groups(cfg, groups, 4*1024*1024)
            runner = GPUModelRunner(cfg, torch.device('cuda'))
            runner.initialize_kv_cache(kvconfig)
            eagle = runner.speculator
            # Every physical block stores the position's value. Zero Q/K means
            # exact uniform attention: mean V = (sequence_length + 1) / 2.
            cache = torch.zeros((64, 2, 16, 1, 128), dtype=torch.float16, device='cuda')
            scheduler_output = SchedulerOutput.make_empty()
            for req, blockbase in enumerate((10, 40)):
                ids = list(range(blockbase, blockbase+8))
                prompt = list(range(1, lengths[req] + 1))
                req_id = f'eagle-request-{req}'
                scheduler_output.scheduled_new_reqs.append(NewRequestData(
                    req_id=req_id, prompt_token_ids=prompt, prefill_token_ids=prompt,
                    mm_features=[], sampling_params=SamplingParams(
                        temperature=0, max_tokens=8, ignore_eos=True),
                    pooling_params=None, block_ids=(ids,), num_computed_tokens=0,
                    lora_request=None))
                scheduler_output.num_scheduled_tokens[req_id] = len(prompt)
                for logical, physical in enumerate(ids):
                    cache[physical, 1, :, 0, :] = torch.arange(
                        logical*16+1, logical*16+17, device='cuda')[:, None]
            scheduler_output.total_num_scheduled_tokens = sum(lengths)
            runner.add_requests(scheduler_output)
            runner.update_requests(scheduler_output)
            runner.block_tables.apply_staged_writes()
            if flashinfer.get_kv_cache_layout() == 'HND':
                cache = cache.permute(0, 1, 3, 2, 4).contiguous().permute(0, 1, 3, 2, 4)
            # The target batch and all metadata/mirrors come from the production
            # scheduler-message preparation boundary, never from dummy edits.
            batch = runner.prepare_inputs(scheduler_output, sum(lengths))
            observed = []

            class Draft(torch.nn.Module):
                calls = 0

                def forward(self, input_ids, positions, hidden_states):
                    metadata = get_forward_context().attn_metadata
                    if self.calls == 0:
                        result = torch.full_like(hidden_states, 0.5)
                    else:
                        selected = metadata[layer]
                        q = torch.zeros((len(input_ids), 4, 128),
                                        dtype=torch.float16, device='cuda')
                        key = torch.zeros((len(input_ids), 1, 128),
                                          dtype=torch.float16, device='cuda')
                        value = (positions + 1).to(torch.float16)[:, None, None].expand_as(key).contiguous()
                        result = attention_layer.impl.forward(
                            attention_layer, q, key, value, cache, selected,
                            output=torch.empty_like(q)).reshape(-1, 512)
                        observed.append(result[:, 0].cpu().tolist())
                    self.calls += 1
                    return result, result

                def compute_logits(self, hidden):
                    token = (2*hidden[:, 0]).round().long().clamp(0, 255)
                    logits = torch.full((len(hidden), 256), -1000., device='cuda')
                    logits.scatter_(1, token[:, None], 1000.)
                    return logits

            eagle.model = Draft()
            result = eagle.propose(batch,
                torch.zeros((sum(lengths), 512), dtype=torch.float16, device='cuda'), None,
                torch.ones(2, dtype=torch.int32, device='cuda'),
                torch.zeros(2, dtype=torch.int32, device='cuda'),
                torch.ones(2, dtype=torch.int32, device='cuda'),
                torch.ones(2, dtype=torch.int32, device='cuda'),
                torch.zeros(2, device='cuda'), torch.zeros(2, dtype=torch.int64, device='cuda'))
            torch.cuda.synchronize()
            expected = [[1] + [n+step+1 for step in range(1, steps)] for n in lengths]
            return {'lengths': lengths, 'steps': steps, 'draft_tokens': result.cpu().tolist(),
                    'expected': expected, 'attention_outputs': observed,
                    'passed': result.cpu().tolist() == expected}


def check_eagle_nondcp():
    results = []
    # Only group metadata is substituted; no collectives are used by non-DCP.
    # Restore every alias, because other scored cases run in the same process.
    with ExitStack() as stack:
        for module in (distributed, parallel_state, table_module, flashinfer,
                       runner_module, graph_module):
            stack.enter_context(patch.object(module, 'get_dcp_group',
                                             return_value=GROUP, create=True))
        for lengths in ([4, 7], [15, 23]):
            result = _run_case(lengths)
            results.append(result)
            print('EAGLE_NON_DCP_CASE=' + json.dumps(result), flush=True)
            if not result['passed']:
                raise AssertionError(
                    f"non-DCP Eagle two-step draft mismatch for lengths {lengths}: "
                    f"expected {result['expected']}, got {result['draft_tokens']}")
    return results


if __name__ == '__main__':
    check_eagle_nondcp()
