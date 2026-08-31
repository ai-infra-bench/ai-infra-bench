"""Verifier-owned AsyncScheduler construction and output-frame driving."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import torch

from vllm import SamplingParams
from vllm.config import (
    CacheConfig,
    ModelConfig,
    ParallelConfig,
    SchedulerConfig,
    VllmConfig,
)
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.async_scheduler import AsyncScheduler
from vllm.v1.core.sched.output import CachedRequestData, SchedulerOutput
from vllm.v1.core.single_type_kv_cache_manager import register_all_kvcache_specs
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus
from vllm.v1.structured_output import StructuredOutputManager


BLOCK_SIZE = 16
_hash_initialized = False


@dataclass(frozen=True)
class RequestSnapshot:
    placeholders: int
    computed_tokens: int
    output_tokens: tuple[int, ...]
    status: RequestStatus


def tiny_model(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["OPTForCausalLM"],
                "model_type": "opt",
                "hidden_size": 64,
                "ffn_dim": 256,
                "num_attention_heads": 4,
                "num_hidden_layers": 2,
                "vocab_size": 4096,
                "max_position_embeddings": 2048,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    return path


def make_scheduler(model_dir: Path, *, max_num_seqs=32) -> AsyncScheduler:
    model_config = ModelConfig(
        model=str(tiny_model(model_dir)),
        dtype="float16",
        skip_tokenizer_init=True,
        max_model_len=2048,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=max_num_seqs,
        max_num_batched_tokens=2048,
        max_model_len=2048,
        enable_chunked_prefill=True,
        async_scheduling=True,
        is_encoder_decoder=False,
        watermark=0.0,
    )
    cache_config = CacheConfig(
        block_size=BLOCK_SIZE,
        gpu_memory_utilization=0.5,
        enable_prefix_caching=False,
    )
    cache_config.num_gpu_blocks = 10000
    config = VllmConfig(
        model_config=model_config,
        scheduler_config=scheduler_config,
        cache_config=cache_config,
        parallel_config=ParallelConfig(pipeline_parallel_size=1),
    )
    kv_config = KVCacheConfig(
        num_blocks=10000,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=BLOCK_SIZE,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            )
        ],
    )
    register_all_kvcache_specs(config)
    scheduler = AsyncScheduler(
        vllm_config=config,
        kv_cache_config=kv_config,
        block_size=BLOCK_SIZE,
        log_stats=False,
        structured_output_manager=StructuredOutputManager(config),
    )
    scheduler.use_v2_model_runner = False
    return scheduler


def make_requests(count: int, *, max_tokens=128, token_seed=0):
    global _hash_initialized
    if not _hash_initialized:
        init_none_hash(sha256)
        _hash_initialized = True
    hasher = get_request_block_hasher(BLOCK_SIZE, sha256)
    requests = []
    for index in range(count):
        prompt = [token_seed + index + 1] * 10
        requests.append(
            Request(
                request_id=f"request-{token_seed}-{index}",
                prompt_token_ids=prompt,
                sampling_params=SamplingParams(max_tokens=max_tokens, ignore_eos=True),
                pooling_params=None,
                mm_features=None,
                block_hasher=hasher,
            )
        )
    return requests


def activate_requests(scheduler: AsyncScheduler, requests: list[Request]):
    for request in requests:
        request.append_output_token_ids(42)
        scheduler.add_request(request)
        request.num_computed_tokens = request.num_tokens - 1


def prepare_for_schedule(requests: list[Request]):
    for request in requests:
        request.num_computed_tokens = request.num_tokens - 1


def capture_spec_frame(
    scheduler: AsyncScheduler,
    requests: list[Request],
    *,
    num_drafts: int,
    num_accepted: int,
) -> SchedulerOutput:
    prepare_for_schedule(requests)
    output = scheduler.schedule()
    expected_ids = {request.request_id for request in requests}
    assert set(output.num_scheduled_tokens) == expected_ids
    for request in requests:
        request_id = request.request_id
        output.scheduled_spec_decode_tokens[request_id] = list(
            range(100, 100 + num_drafts)
        )
        output.num_scheduled_tokens[request_id] = num_drafts + 1
        request.num_output_placeholders += num_drafts
    output.total_num_scheduled_tokens = len(requests) * (num_drafts + 1)
    output._verifier_num_accepted = num_accepted
    return output


def resume_after_reset(scheduler: AsyncScheduler, requests: list[Request]):
    assert scheduler.reset_prefix_cache(reset_running_requests=True) is True
    assert all(request.num_output_placeholders == 0 for request in requests)
    prepare_for_schedule(requests)
    output = scheduler.schedule()
    assert set(output.num_scheduled_tokens) == {
        request.request_id for request in requests
    }
    return output


def model_output(
    scheduler_output: SchedulerOutput,
    *,
    accepted: int | None = None,
    empty: bool = False,
    token_seed: int = 900,
) -> ModelRunnerOutput:
    request_ids = list(scheduler_output.num_scheduled_tokens)
    if accepted is None:
        accepted = getattr(scheduler_output, "_verifier_num_accepted", 0)
    sampled = []
    for index, _request_id in enumerate(request_ids):
        if empty:
            sampled.append([])
        else:
            sampled.append(
                list(
                    range(
                        token_seed + index * 20,
                        token_seed + index * 20 + 1 + accepted,
                    )
                )
            )
    return ModelRunnerOutput(
        req_ids=request_ids,
        req_id_to_index={req_id: index for index, req_id in enumerate(request_ids)},
        sampled_token_ids=sampled,
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )


def deliver(
    scheduler: AsyncScheduler,
    scheduler_output: SchedulerOutput,
    *,
    accepted: int | None = None,
    empty: bool = False,
    token_seed: int = 900,
):
    scheduler.update_from_output(
        scheduler_output,
        model_output(
            scheduler_output,
            accepted=accepted,
            empty=empty,
            token_seed=token_seed,
        ),
    )


def snapshot(request: Request) -> RequestSnapshot:
    return RequestSnapshot(
        placeholders=request.num_output_placeholders,
        computed_tokens=request.num_computed_tokens,
        output_tokens=tuple(request.output_token_ids),
        status=request.status,
    )


def assert_stale_frame_did_not_change_fresh_state(
    request: Request, before: RequestSnapshot
):
    after = snapshot(request)
    assert after == before
    assert after.placeholders >= 0


def manual_running_scheduler(
    model_dir: Path,
    *,
    count=1,
):
    scheduler = make_scheduler(model_dir, max_num_seqs=max(32, count))
    requests = make_requests(count)
    for request in requests:
        request.num_computed_tokens = request.num_tokens
        scheduler.requests[request.request_id] = request
        scheduler.running.append(request)
        request.status = RequestStatus.RUNNING
    return scheduler, requests


def synthetic_frame(cases):
    scheduled = {}
    spec = {}
    request_ids = []
    sampled = []
    for request, drafts, accepted in cases:
        request_ids.append(request.request_id)
        scheduled[request.request_id] = drafts + 1
        if drafts:
            spec[request.request_id] = list(range(100, 100 + drafts))
        sampled.append(list(range(900, 901 + accepted)))
    scheduler_output = SchedulerOutput(
        scheduled_new_reqs=[],
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens=scheduled,
        total_num_scheduled_tokens=sum(scheduled.values()),
        scheduled_encoder_inputs={},
        scheduled_spec_decode_tokens=spec,
        num_common_prefix_blocks=[],
        finished_req_ids=set(),
        free_encoder_mm_hashes=[],
    )
    runner_output = ModelRunnerOutput(
        req_ids=request_ids,
        req_id_to_index={req_id: index for index, req_id in enumerate(request_ids)},
        sampled_token_ids=sampled,
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )
    return scheduler_output, runner_output
