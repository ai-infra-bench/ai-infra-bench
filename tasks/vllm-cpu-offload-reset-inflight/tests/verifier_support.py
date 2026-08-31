"""Verifier-owned construction and transfer driving for CPU offload tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import torch

from vllm import SamplingParams
from vllm.config import (
    CacheConfig,
    DeviceConfig,
    KVTransferConfig,
    ModelConfig,
    ParallelConfig,
    SchedulerConfig,
    VllmConfig,
)
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_manager import KVCacheBlocks
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.output import (
    CachedRequestData,
    NewRequestData,
    SchedulerOutput,
)
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.core.single_type_kv_cache_manager import register_all_kvcache_specs
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    KVCacheTensor,
)
from vllm.v1.outputs import KVConnectorOutput
from vllm.v1.request import Request
from vllm.v1.simple_kv_offload.metadata import SimpleCPUOffloadWorkerMetadata
from vllm.v1.structured_output import StructuredOutputManager


BLOCK_SIZE = 16
HEAD_SIZE = 16
NUM_KV_HEADS = 1
DTYPE = torch.float16
BYTES_PER_BLOCK = (
    BLOCK_SIZE * NUM_KV_HEADS * HEAD_SIZE * 2 * DTYPE.itemsize
)

_hash_initialized = False


@dataclass
class Harness:
    scheduler: Scheduler
    connector: object
    gpu_pool: object
    lazy: bool
    worker_count: int


@dataclass(frozen=True)
class TransferHandle:
    kind: str
    token: int | str


def _tiny_model(path: Path) -> Path:
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
                "max_position_embeddings": 10000,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float16",
            }
        )
    )
    return path


def _kv_cache_config(num_blocks: int) -> KVCacheConfig:
    register_all_kvcache_specs(vllm_config=None)
    layer_names = ["layer"]
    return KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[
            KVCacheTensor(
                size=BYTES_PER_BLOCK * num_blocks,
                shared_by=layer_names,
            )
        ],
        kv_cache_groups=[
            KVCacheGroupSpec(
                layer_names,
                FullAttentionSpec(
                    block_size=BLOCK_SIZE,
                    num_kv_heads=NUM_KV_HEADS,
                    head_size=HEAD_SIZE,
                    dtype=DTYPE,
                ),
            )
        ],
    )


def make_harness(
    model_dir: Path,
    *,
    lazy: bool,
    num_cpu_blocks: int = 24,
    num_gpu_blocks: int = 40,
    worker_count: int = 1,
) -> Harness:
    model_config = ModelConfig(
        model=str(_tiny_model(model_dir)),
        dtype="float16",
        skip_tokenizer_init=True,
        max_model_len=10000,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=32,
        max_num_batched_tokens=64,
        max_model_len=10000,
        enable_chunked_prefill=True,
        is_encoder_decoder=False,
    )
    cache_config = CacheConfig(
        block_size=BLOCK_SIZE,
        gpu_memory_utilization=0.5,
        enable_prefix_caching=True,
    )
    cache_config.num_gpu_blocks = num_gpu_blocks
    transfer_config = KVTransferConfig(
        kv_connector="SimpleCPUOffloadConnector",
        kv_role="kv_both",
        kv_buffer_device="cpu",
        kv_connector_extra_config={
            "cpu_bytes_to_use": BYTES_PER_BLOCK * num_cpu_blocks * worker_count,
            "lazy_offload": lazy,
        },
    )
    config = VllmConfig(
        model_config=model_config,
        scheduler_config=scheduler_config,
        cache_config=cache_config,
        device_config=DeviceConfig("cpu"),
        parallel_config=ParallelConfig(pipeline_parallel_size=worker_count),
        kv_transfer_config=transfer_config,
    )
    kv_config = _kv_cache_config(num_gpu_blocks)
    scheduler = Scheduler(
        vllm_config=config,
        kv_cache_config=kv_config,
        structured_output_manager=StructuredOutputManager(config),
        block_size=BLOCK_SIZE,
        log_stats=False,
    )
    assert scheduler.connector is not None
    return Harness(
        scheduler=scheduler,
        connector=scheduler.connector,
        gpu_pool=scheduler.kv_cache_manager.block_pool,
        lazy=lazy,
        worker_count=worker_count,
    )


def make_request(
    request_id: str,
    *,
    num_blocks: int,
    token_seed: int,
    prompt_token_ids: list[int] | None = None,
) -> Request:
    global _hash_initialized
    if not _hash_initialized:
        init_none_hash(sha256)
        _hash_initialized = True
    if prompt_token_ids is None:
        prompt_token_ids = list(
            range(token_seed, token_seed + num_blocks * BLOCK_SIZE + 1)
        )
    return Request(
        request_id=request_id,
        prompt_token_ids=list(prompt_token_ids),
        sampling_params=SamplingParams(max_tokens=1),
        pooling_params=None,
        mm_features=None,
        block_hasher=get_request_block_hasher(BLOCK_SIZE, sha256),
    )


def matching_request(source: Request, request_id: str) -> Request:
    assert source.prompt_token_ids is not None
    return make_request(
        request_id,
        num_blocks=max(1, len(source.prompt_token_ids) // BLOCK_SIZE),
        token_seed=0,
        prompt_token_ids=list(source.prompt_token_ids),
    )


def _scheduler_output(
    scheduled_tokens: dict[str, int],
    new_reqs: dict[str, tuple[list[int], ...]] | None = None,
) -> SchedulerOutput:
    new_data = []
    for request_id, block_ids in (new_reqs or {}).items():
        new_data.append(
            NewRequestData(
                req_id=request_id,
                prompt_token_ids=None,
                mm_features=[],
                sampling_params=None,
                pooling_params=None,
                block_ids=block_ids,
                num_computed_tokens=0,
                lora_request=None,
            )
        )
    return SchedulerOutput(
        scheduled_new_reqs=new_data,
        scheduled_cached_reqs=CachedRequestData.make_empty(),
        num_scheduled_tokens=scheduled_tokens,
        total_num_scheduled_tokens=sum(scheduled_tokens.values()),
        scheduled_spec_decode_tokens={},
        scheduled_encoder_inputs={},
        num_common_prefix_blocks=[],
        preempted_req_ids=set(),
        finished_req_ids=set(),
        free_encoder_mm_hashes=[],
    )


def _allocate_cached_gpu_blocks(harness: Harness, request: Request, num_blocks: int):
    blocks = harness.gpu_pool.get_new_blocks(num_blocks)
    harness.gpu_pool.cache_full_blocks(
        request=request,
        blocks=blocks,
        num_cached_blocks=0,
        num_full_blocks=num_blocks,
        block_size=BLOCK_SIZE,
        kv_cache_group_id=0,
    )
    return blocks


def _start_eager_store(harness: Harness, request: Request, num_blocks: int):
    blocks = _allocate_cached_gpu_blocks(harness, request, num_blocks)
    request.num_computed_tokens = num_blocks * BLOCK_SIZE
    kv_blocks = KVCacheBlocks(blocks=(blocks,))
    harness.connector.update_state_after_alloc(
        request, kv_blocks, num_external_tokens=0
    )
    metadata = harness.connector.build_connector_meta(
        _scheduler_output(
            {request.request_id: num_blocks * BLOCK_SIZE},
            {request.request_id: kv_blocks.get_block_ids()},
        )
    )
    harness.gpu_pool.free_blocks(blocks)
    return TransferHandle("store", metadata.store_event)


def _start_lazy_store(harness: Harness, request: Request, num_blocks: int):
    blocks = _allocate_cached_gpu_blocks(harness, request, num_blocks)
    harness.gpu_pool.free_blocks(blocks)
    filler_count = harness.gpu_pool.get_num_free_blocks() - num_blocks
    fillers = harness.gpu_pool.get_new_blocks(filler_count)
    metadata = harness.connector.build_connector_meta(_scheduler_output({}))
    harness.gpu_pool.free_blocks(fillers)
    return TransferHandle("store", metadata.store_event)


def start_store(harness: Harness, request: Request, num_blocks: int):
    if harness.lazy:
        return _start_lazy_store(harness, request, num_blocks)
    return _start_eager_store(harness, request, num_blocks)


def complete_transfer(harness: Harness, transfer: TransferHandle, count=None):
    if transfer.kind == "load":
        output = KVConnectorOutput(
            finished_sending=set(),
            finished_recving={str(transfer.token)},
        )
    else:
        output = KVConnectorOutput(
            finished_recving=set(),
            kv_connector_worker_meta=SimpleCPUOffloadWorkerMetadata(
                completed_store_events={
                    int(transfer.token): harness.worker_count if count is None else count
                }
            ),
        )
    harness.connector.update_connector_output(output)


def populate_cache(harness: Harness, request: Request, num_blocks: int):
    transfer = start_store(harness, request, num_blocks)
    complete_transfer(harness, transfer)


def observed_hit(harness: Harness, source: Request, suffix: str):
    probe = matching_request(source, f"probe-{suffix}")
    hit_tokens, async_load = harness.connector.get_num_new_matched_tokens(probe, 0)
    harness.connector.request_finished(probe, [])
    return hit_tokens, async_load


def start_load(harness: Harness, source: Request, request_id: str):
    loading = matching_request(source, request_id)
    hit_tokens, async_load = harness.connector.get_num_new_matched_tokens(loading, 0)
    assert hit_tokens and hit_tokens > 0 and async_load
    blocks = harness.gpu_pool.get_new_blocks(hit_tokens // BLOCK_SIZE)
    kv_blocks = KVCacheBlocks(blocks=(blocks,))
    harness.connector.update_state_after_alloc(
        loading, kv_blocks, num_external_tokens=hit_tokens
    )
    metadata = harness.connector.build_connector_meta(
        _scheduler_output(
            {loading.request_id: 1},
            {loading.request_id: kv_blocks.get_block_ids()},
        )
    )
    harness.gpu_pool.free_blocks(blocks)
    return loading, TransferHandle("load", loading.request_id), metadata


def reset(harness: Harness, *, reset_connector=True):
    return harness.scheduler.reset_prefix_cache(reset_connector=reset_connector)


def assert_fresh_store_works(harness: Harness, seed: int):
    fresh = make_request(
        f"fresh-{harness.lazy}-{seed}",
        num_blocks=2,
        token_seed=seed,
    )
    populate_cache(harness, fresh, 2)
    hit_tokens, async_load = observed_hit(harness, fresh, f"fresh-{seed}")
    assert hit_tokens == 2 * BLOCK_SIZE
    assert async_load is True
