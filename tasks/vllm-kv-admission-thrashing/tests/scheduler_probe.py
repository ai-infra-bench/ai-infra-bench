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
from vllm.v1.kv_cache_interface import (
    ChunkedLocalAttentionSpec,
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    SlidingWindowSpec,
)
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
                   batch_tokens: int, enable_prefix_caching: bool = False,
                   attention_kind: str = "full",
                   attention_window: int = 64,
                   max_partial_prefills: int = 1,
                   long_prefill_threshold: int = 0) -> Scheduler:
    model_config = ModelConfig(model=tiny_model(tmp_path), trust_remote_code=True,
                               dtype="float16", seed=42, skip_tokenizer_init=True)
    scheduler_config = SchedulerConfig(
        max_num_seqs=16, max_num_batched_tokens=batch_tokens, max_model_len=384,
        enable_chunked_prefill=True, async_scheduling=False,
        max_num_partial_prefills=max_partial_prefills,
        max_long_partial_prefills=max_partial_prefills,
        long_prefill_token_threshold=long_prefill_threshold,
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(block_size=block_size, gpu_memory_utilization=0.9,
                               cache_dtype="auto",
                               enable_prefix_caching=enable_prefix_caching)
    cache_config.num_gpu_blocks = num_blocks
    config = VllmConfig(scheduler_config=scheduler_config, model_config=model_config,
                        cache_config=cache_config,
                        parallel_config=ParallelConfig(pipeline_parallel_size=1))
    spec_args = {
        "block_size": block_size,
        "num_kv_heads": 1,
        "head_size": 1,
        "dtype": torch.float32,
    }
    if attention_kind == "full":
        specs = [("full-layer", FullAttentionSpec(**spec_args))]
    elif attention_kind == "sliding":
        specs = [("sliding-layer", SlidingWindowSpec(
            sliding_window=attention_window, **spec_args))]
    elif attention_kind == "chunked_local":
        specs = [("local-layer", ChunkedLocalAttentionSpec(
            attention_chunk_size=attention_window, **spec_args))]
    elif attention_kind == "hybrid":
        specs = [
            ("full-layer", FullAttentionSpec(**spec_args)),
            ("sliding-layer", SlidingWindowSpec(
                sliding_window=attention_window, **spec_args)),
        ]
    else:
        raise ValueError(f"unknown attention kind: {attention_kind}")
    kv_cache_config = KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec([layer_name], spec) for layer_name, spec in specs
        ],
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


def run_contention_case(tmp_path: Path, case: ContentionCase, *,
                        attention_kind: str = "full",
                        attention_window: int = 64) -> dict:
    scheduler = make_scheduler(tmp_path, num_blocks=case.num_blocks,
                               block_size=case.block_size,
                               batch_tokens=case.batch_tokens,
                               attention_kind=attention_kind,
                               attention_window=attention_window)
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
    preemptions = regressions = rollback_events = steps = 0
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
        rollback_events += int(current < target_progress[-1])
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
        "rollback_events": rollback_events,
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


def run_burst_case(tmp_path: Path, case: ContentionCase,
                   target_prompts: tuple[int, ...]) -> dict:
    scheduler = make_scheduler(tmp_path, num_blocks=case.num_blocks,
                               block_size=case.block_size,
                               batch_tokens=case.batch_tokens,
                               max_partial_prefills=len(target_prompts),
                               long_prefill_threshold=max(
                                   case.block_size, case.batch_tokens // 3))
    incumbent = make_request("decode-incumbent", case.incumbent_prompt, 12,
                             block_size=case.block_size)
    requests = {incumbent.request_id: incumbent}
    scheduler.add_request(incumbent)
    while incumbent.num_output_tokens == 0:
        advance(scheduler, requests)

    targets = []
    progress: dict[str, list[int]] = {}
    for index, prompt_tokens in enumerate(target_prompts):
        target = make_request(f"burst-target-{index}", prompt_tokens, 4,
                              block_size=case.block_size)
        targets.append(target)
        requests[target.request_id] = target
        progress[target.request_id] = [target.num_computed_tokens]
        scheduler.add_request(target)

    steps = 0
    while not all(request.is_finished() for request in targets) and steps < 128:
        advance(scheduler, requests)
        steps += 1
        for target in targets:
            progress[target.request_id].append(target.num_computed_tokens)

    return {
        "incumbent_finished": incumbent.is_finished(),
        "targets_finished": [target.is_finished() for target in targets],
        "target_preemptions": [target.num_preemptions for target in targets],
        "rollback_events": [
            sum(current < previous for previous, current in zip(values, values[1:]))
            for values in progress.values()
        ],
        "steps": steps,
    }
