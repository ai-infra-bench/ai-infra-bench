from __future__ import annotations

import json
from pathlib import Path
import torch

from vllm.config import CacheConfig, ModelConfig, SchedulerConfig, VllmConfig
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.async_scheduler import AsyncScheduler
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.core.single_type_kv_cache_manager import register_all_kvcache_specs
from vllm.v1.kv_cache_interface import (
    ChunkedLocalAttentionSpec,
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    SlidingWindowSpec,
)
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus
from vllm.v1.structured_output import StructuredOutputManager


BLOCK_SIZE = 16
PROMPT_TOKENS = 100
_hash_ready = False


def tiny_model(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    config = path / "config.json"
    if not config.exists():
        config.write_text(
            json.dumps(
                {
                    "architectures": ["OPTForCausalLM"],
                    "model_type": "opt",
                    "hidden_size": 64,
                    "ffn_dim": 128,
                    "num_attention_heads": 4,
                    "num_hidden_layers": 1,
                    "vocab_size": 128,
                    "max_position_embeddings": 512,
                    "word_embed_proj_dim": 64,
                }
            )
        )
    return str(path)


def spec(kind: str):
    common = {
        "block_size": BLOCK_SIZE,
        "num_kv_heads": 1,
        "head_size": 1,
        "dtype": torch.float32,
    }
    if kind == "swa":
        return SlidingWindowSpec(**common, sliding_window=16)
    if kind == "chunked":
        return ChunkedLocalAttentionSpec(**common, attention_chunk_size=32)
    if kind == "full":
        return FullAttentionSpec(**common)
    raise AssertionError(kind)


def make_vllm_config(path: Path, *, async_scheduling: bool) -> VllmConfig:
    model = ModelConfig(
        model=tiny_model(path),
        dtype="float16",
        skip_tokenizer_init=True,
    )
    config = VllmConfig(
        model_config=model,
        scheduler_config=SchedulerConfig(
            max_num_seqs=8,
            max_num_batched_tokens=256,
            max_model_len=512,
            enable_chunked_prefill=True,
            async_scheduling=async_scheduling,
            is_encoder_decoder=model.is_encoder_decoder,
            watermark=0.0,
        ),
        cache_config=CacheConfig(
            block_size=BLOCK_SIZE,
            gpu_memory_utilization=0.9,
            cache_dtype="auto",
            enable_prefix_caching=False,
        ),
    )
    config.scheduler_config.async_scheduling = async_scheduling
    return config


def make_scheduler(path: Path, kind: str, *, async_scheduling: bool):
    config = make_vllm_config(path, async_scheduling=async_scheduling)
    config.cache_config.num_gpu_blocks = 128
    kv_config = KVCacheConfig(
        num_blocks=128,
        kv_cache_tensors=[],
        kv_cache_groups=[KVCacheGroupSpec(["layer"], spec(kind))],
    )
    register_all_kvcache_specs(config)
    cls = AsyncScheduler if async_scheduling else Scheduler
    return (
        cls(
            vllm_config=config,
            kv_cache_config=kv_config,
            block_size=BLOCK_SIZE,
            log_stats=True,
            structured_output_manager=StructuredOutputManager(config),
        ),
        config,
    )


def make_request(name: str, *, max_tokens: int = 8) -> Request:
    global _hash_ready
    if not _hash_ready:
        init_none_hash(sha256)
        _hash_ready = True
    params = SamplingParams(max_tokens=max_tokens)
    params.update_from_generation_config({}, 127)
    return Request(
        request_id=name,
        prompt_token_ids=[1] * PROMPT_TOKENS,
        sampling_params=params,
        pooling_params=None,
        block_hasher=get_request_block_hasher(BLOCK_SIZE, sha256),
    )


def runner_output(scheduler_output) -> ModelRunnerOutput:
    ids = list(scheduler_output.num_scheduled_tokens)
    return ModelRunnerOutput(
        req_ids=ids,
        req_id_to_index={name: index for index, name in enumerate(ids)},
        sampled_token_ids=[[1]] * len(ids),
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )


def block_ids(scheduler, request_id: str) -> list[int]:
    return list(scheduler.kv_cache_manager.get_block_ids(request_id)[0])


def async_free_timeline(path: Path, kind: str) -> dict[str, int]:
    scheduler, _ = make_scheduler(path, kind, async_scheduling=True)
    item = make_request(f"{kind}-async")
    scheduler.add_request(item)
    pool = scheduler.kv_cache_manager.block_pool
    prefill = scheduler.schedule()
    after_prefill = pool.get_num_free_blocks()
    decode = scheduler.schedule()
    before_process = pool.get_num_free_blocks()
    scheduler.update_from_output(prefill, runner_output(prefill))
    scheduler.schedule()
    after_process = pool.get_num_free_blocks()
    scheduler.update_from_output(decode, runner_output(decode))
    scheduler.schedule()
    after_next = pool.get_num_free_blocks()
    return {
        "after_prefill": after_prefill,
        "before_process": before_process,
        "after_process": after_process,
        "after_next": after_next,
    }


def sync_free_timeline(path: Path, kind: str) -> dict[str, int]:
    scheduler, _ = make_scheduler(path, kind, async_scheduling=False)
    item = make_request(f"{kind}-sync")
    scheduler.add_request(item)
    pool = scheduler.kv_cache_manager.block_pool
    prefill = scheduler.schedule()
    scheduler.update_from_output(prefill, runner_output(prefill))
    before_decode = pool.get_num_free_blocks()
    scheduler.schedule()
    after_decode = pool.get_num_free_blocks()
    return {"before_decode": before_decode, "after_decode": after_decode}


def connector_handoff_block_count(path: Path) -> int:
    scheduler, _ = make_scheduler(path, "swa", async_scheduling=True)
    item = make_request("connector-handoff")
    scheduler.add_request(item)
    scheduler.schedule()
    scheduler.schedule()
    class RecordingConnector:
        def __init__(self) -> None:
            self.block_ids = None

        def request_finished(self, _request, block_ids):
            self.block_ids = block_ids
            return False, None

    connector = RecordingConnector()
    scheduler.connector = connector
    scheduler.finish_requests(item.request_id, RequestStatus.FINISHED_ABORTED)
    assert connector.block_ids is not None
    return len(connector.block_ids)


def competing_load_reuse(path: Path, kind: str) -> dict[str, object]:
    """Model an external load destination with a competing request.

    The target scheduler and real block pool run unchanged. Model execution and
    the external DMA are substituted: allocation to ``load-target`` represents
    the connector choosing destination blocks for an incoming KV load.
    """
    scheduler, _ = make_scheduler(path, kind, async_scheduling=True)
    reader = make_request("inflight-reader", max_tokens=64)
    scheduler.add_request(reader)
    scheduler.schedule()
    reader_blocks = set(block_ids(scheduler, reader.request_id))

    # Scheduling again before processing the first output is the vulnerable
    # overlap. A competing request then asks the same real block pool for load
    # destinations.
    scheduler.schedule()
    load_target = make_request("load-target")
    scheduler.add_request(load_target)
    scheduler.schedule()
    load_blocks = set(block_ids(scheduler, load_target.request_id))
    overlap = sorted(reader_blocks & load_blocks)
    return {
        "reader_blocks": sorted(reader_blocks),
        "load_blocks": sorted(load_blocks),
        "premature_overlap": overlap,
    }


def speculative_rollback_window(
    path: Path,
    kind: str,
    *,
    rollback_tokens: int,
) -> dict[str, object]:
    """Inject a deterministic speculative rejection at the scheduler boundary."""
    scheduler, _ = make_scheduler(path, kind, async_scheduling=True)
    item = make_request("rollback", max_tokens=64)
    scheduler.add_request(item)
    scheduler.schedule()
    original = block_ids(scheduler, item.request_id)

    # The next schedule advances the optimistic count while the preceding step
    # is still in flight. Rejection then moves progress back into that range.
    scheduler.schedule()
    optimistic = item.num_computed_tokens
    assert 0 < rollback_tokens < optimistic
    item.num_computed_tokens -= rollback_tokens
    rolled_back = item.num_computed_tokens

    if kind == "swa":
        first_required_token = max(0, rolled_back - 16 + 1)
    elif kind == "chunked":
        first_required_token = (rolled_back // 32) * 32
    else:
        raise AssertionError(kind)
    first_block = first_required_token // BLOCK_SIZE
    last_block = max(first_block, (rolled_back - 1) // BLOCK_SIZE)
    current = block_ids(scheduler, item.request_id)
    required_original = original[first_block : last_block + 1]
    required_current = current[first_block : last_block + 1]
    return {
        "optimistic_tokens": optimistic,
        "rolled_back_tokens": rolled_back,
        "required_block_indexes": list(range(first_block, last_block + 1)),
        "required_original_ids": required_original,
        "required_current_ids": required_current,
        "required_blocks_retained": required_current == required_original,
    }


def admission_blocks(path: Path, kind: str, *, async_scheduling: bool) -> int:
    config = make_vllm_config(path, async_scheduling=async_scheduling)
    item_spec = spec(kind)
    return item_spec.max_memory_usage_bytes(config) // item_spec.page_size_bytes
