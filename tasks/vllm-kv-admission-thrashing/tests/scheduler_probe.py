from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import torch

from vllm.config import CacheConfig, ModelConfig, ParallelConfig, SchedulerConfig, VllmConfig
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import FullAttentionSpec, KVCacheConfig, KVCacheGroupSpec
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request
from vllm.v1.structured_output import StructuredOutputManager


EOS_TOKEN_ID = 3
_hash_initialized = False


@dataclass(frozen=True)
class ContentionCase:
    num_blocks: int
    block_size: int
    batch_tokens: int
    incumbent_prompt: int
    target_prompt: int


def tiny_model(tmp_path: Path) -> str:
    model_dir = tmp_path / "tiny-opt"
    model_dir.mkdir(exist_ok=True)
    config = model_dir / "config.json"
    if not config.exists():
        config.write_text(json.dumps({
            "architectures": ["OPTForCausalLM"], "model_type": "opt",
            "hidden_size": 128, "ffn_dim": 256, "num_attention_heads": 4,
            "num_hidden_layers": 1, "vocab_size": 256,
            "max_position_embeddings": 512, "word_embed_proj_dim": 128,
            "do_layer_norm_before": True, "torch_dtype": "float32",
        }))
    return str(model_dir)


def make_scheduler(tmp_path: Path, *, num_blocks: int, block_size: int,
                   batch_tokens: int, enable_prefix_caching: bool = False) -> Scheduler:
    model_config = ModelConfig(model=tiny_model(tmp_path), trust_remote_code=True,
                               dtype="float16", seed=42, skip_tokenizer_init=True)
    scheduler_config = SchedulerConfig(
        max_num_seqs=16, max_num_batched_tokens=batch_tokens, max_model_len=256,
        enable_chunked_prefill=True, async_scheduling=False,
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(block_size=block_size, gpu_memory_utilization=0.9,
                               cache_dtype="auto",
                               enable_prefix_caching=enable_prefix_caching)
    cache_config.num_gpu_blocks = num_blocks
    config = VllmConfig(scheduler_config=scheduler_config, model_config=model_config,
                        cache_config=cache_config,
                        parallel_config=ParallelConfig(pipeline_parallel_size=1))
    kv_cache_config = KVCacheConfig(
        num_blocks=num_blocks, kv_cache_tensors=[],
        kv_cache_groups=[KVCacheGroupSpec(
            ["layer"], FullAttentionSpec(block_size=block_size, num_kv_heads=1,
                                          head_size=1, dtype=torch.float32))],
    )
    return Scheduler(vllm_config=config, kv_cache_config=kv_cache_config,
                     block_size=block_size, log_stats=True,
                     structured_output_manager=StructuredOutputManager(config))


def make_request(request_id: str, num_tokens: int, max_tokens: int, *,
                 block_size: int, same_prompt: bool = False) -> Request:
    global _hash_initialized
    if not _hash_initialized:
        init_none_hash(sha256)
        _hash_initialized = True
    sampling = SamplingParams(max_tokens=max_tokens)
    sampling.update_from_generation_config({}, EOS_TOKEN_ID)
    token = 0 if same_prompt else (sum(request_id.encode()) % 251) + 1
    return Request(request_id=request_id, prompt_token_ids=[token] * num_tokens,
                   sampling_params=sampling, pooling_params=None,
                   block_hasher=get_request_block_hasher(block_size, sha256))


def advance(scheduler: Scheduler, requests: dict[str, Request]):
    output = scheduler.schedule()
    ids = list(output.num_scheduled_tokens)
    sampled = []
    for request_id in ids:
        request = requests[request_id]
        completes_prompt = (request.num_computed_tokens
                            + output.num_scheduled_tokens[request_id]
                            >= request.num_prompt_tokens)
        sampled.append([1000] if completes_prompt else [])
    scheduler.update_from_output(output, ModelRunnerOutput(
        req_ids=ids, req_id_to_index={rid: i for i, rid in enumerate(ids)},
        sampled_token_ids=sampled, logprobs=None, prompt_logprobs_dict={},
        pooler_output=[]))
    return output


def run_contention_case(tmp_path: Path, case: ContentionCase) -> dict:
    scheduler = make_scheduler(tmp_path, num_blocks=case.num_blocks,
                               block_size=case.block_size,
                               batch_tokens=case.batch_tokens)
    incumbent = make_request("decode-incumbent", case.incumbent_prompt, 8,
                             block_size=case.block_size)
    requests = {incumbent.request_id: incumbent}
    scheduler.add_request(incumbent)
    while incumbent.num_output_tokens == 0:
        advance(scheduler, requests)
    target = make_request("long-target", case.target_prompt, 4,
                          block_size=case.block_size)
    requests[target.request_id] = target
    scheduler.add_request(target)
    preemptions = regressions = steps = 0
    max_progress = target.num_computed_tokens
    incumbent_progress = [incumbent.num_output_tokens]
    target_progress = [target.num_computed_tokens]
    concurrent_progress = False
    while not target.is_finished() and steps < 64:
        incumbent_active = not incumbent.is_finished()
        output = advance(scheduler, requests)
        steps += 1
        preemptions += int(target.request_id in output.preempted_req_ids)
        current = target.num_computed_tokens
        regressions += int(current < max_progress)
        max_progress = max(max_progress, current)
        if incumbent_active and current > target_progress[-1]:
            concurrent_progress = True
        target_progress.append(current)
        incumbent_progress.append(incumbent.num_output_tokens)
    return {
        "target_finished": target.is_finished(),
        "incumbent_finished": incumbent.is_finished(),
        "target_preemptions": preemptions,
        "request_preemption_count": target.num_preemptions,
        "progress_regressions": regressions,
        "target_progress": target_progress,
        "incumbent_progress": incumbent_progress,
        "target_progress_while_incumbent_active": concurrent_progress,
        "steps": steps,
    }


def run_prefix_case(tmp_path: Path, *, num_blocks: int, block_size: int,
                    batch_tokens: int, seed_tokens: int, target_tokens: int) -> dict:
    scheduler = make_scheduler(tmp_path, num_blocks=num_blocks, block_size=block_size,
                               batch_tokens=batch_tokens,
                               enable_prefix_caching=True)
    seed = make_request("prefix-seed", seed_tokens, 1, block_size=block_size,
                        same_prompt=True)
    requests = {seed.request_id: seed}
    scheduler.add_request(seed)
    while not seed.is_finished():
        advance(scheduler, requests)
    target = make_request("prefix-target", target_tokens, 4, block_size=block_size,
                          same_prompt=True)
    requests[target.request_id] = target
    scheduler.add_request(target)
    first = advance(scheduler, requests)
    first_scheduled = first.num_scheduled_tokens.get(target.request_id, 0)
    new_request = next((item for item in first.scheduled_new_reqs
                        if item.req_id == target.request_id), None)
    cached_tokens = new_request.num_computed_tokens if new_request else 0
    steps = 1
    while not target.is_finished() and steps < 64:
        advance(scheduler, requests)
        steps += 1
    return {"first_scheduled": first_scheduled, "cached_tokens": cached_tokens,
            "target_finished": target.is_finished(),
            "target_preemptions": target.num_preemptions, "steps": steps}
