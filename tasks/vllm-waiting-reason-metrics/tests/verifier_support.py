from __future__ import annotations

import json
from pathlib import Path

import torch
from prometheus_client import generate_latest

from vllm.config import (
    CacheConfig,
    ModelConfig,
    ParallelConfig,
    SchedulerConfig,
    VllmConfig,
)
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.metrics.loggers import PrometheusStatLogger
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request, RequestStatus
from vllm.v1.structured_output import StructuredOutputManager


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
                    "max_position_embeddings": 256,
                    "word_embed_proj_dim": 64,
                    "do_layer_norm_before": True,
                    "torch_dtype": "float32",
                }
            )
        )
    return str(path)


def make_scheduler(path: Path, capacity_waiting: int) -> tuple[Scheduler, VllmConfig]:
    model_config = ModelConfig(
        model=tiny_model(path),
        dtype="float16",
        seed=42,
        skip_tokenizer_init=True,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=2,
        max_num_batched_tokens=100,
        max_model_len=128,
        enable_chunked_prefill=True,
        async_scheduling=False,
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(
        block_size=16,
        gpu_memory_utilization=0.9,
        cache_dtype="auto",
    )
    cache_config.num_gpu_blocks = 64
    config = VllmConfig(
        scheduler_config=scheduler_config,
        model_config=model_config,
        cache_config=cache_config,
        parallel_config=ParallelConfig(pipeline_parallel_size=1),
    )
    kv_config = KVCacheConfig(
        num_blocks=64,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=16,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            )
        ],
    )
    scheduler = Scheduler(
        vllm_config=config,
        kv_cache_config=kv_config,
        block_size=16,
        log_stats=True,
        structured_output_manager=StructuredOutputManager(config),
    )
    return scheduler, config


def request(request_id: str, *, deferred: bool = False) -> Request:
    global _hash_ready
    if not _hash_ready:
        init_none_hash(sha256)
        _hash_ready = True
    params = SamplingParams(max_tokens=4)
    params.update_from_generation_config({}, 127)
    item = Request(
        request_id=request_id,
        prompt_token_ids=[(sum(request_id.encode()) % 100) + 1] * 50,
        sampling_params=params,
        pooling_params=None,
        block_hasher=get_request_block_hasher(16, sha256),
    )
    if deferred:
        item.status = RequestStatus.WAITING_FOR_REMOTE_KVS
    return item


def scheduler_stats(
    path: Path,
    *,
    capacity: int,
    deferred: int,
) -> tuple[object, VllmConfig]:
    scheduler, config = make_scheduler(path, capacity)
    requests = [
        request(f"capacity-{index}")
        for index in range(capacity + 2)
    ]
    requests.extend(
        request(f"deferred-{index}", deferred=True)
        for index in range(deferred)
    )
    for item in requests:
        scheduler.add_request(item)
    output = scheduler.schedule()
    ids = list(output.num_scheduled_tokens)
    engine_outputs = scheduler.update_from_output(
        output,
        ModelRunnerOutput(
            req_ids=ids,
            req_id_to_index={request_id: i for i, request_id in enumerate(ids)},
            sampled_token_ids=[[1]] * len(ids),
            logprobs=None,
            prompt_logprobs_dict={},
            pooler_output=[],
        ),
    )
    assert engine_outputs
    stats = engine_outputs[0].scheduler_stats
    assert stats is not None
    return stats, config


def scheduled_request_ids(path: Path) -> list[str]:
    scheduler, _ = make_scheduler(path, capacity_waiting=2)
    for index in range(4):
        scheduler.add_request(request(f"capacity-{index}"))
    for index in range(2):
        scheduler.add_request(request(f"deferred-{index}", deferred=True))
    output = scheduler.schedule()
    return list(output.num_scheduled_tokens)


def prometheus_output(
    path: Path,
    scenarios: list[tuple[int, int]],
) -> str:
    first_stats, config = scheduler_stats(
        path / "engine-0",
        capacity=scenarios[0][0],
        deferred=scenarios[0][1],
    )
    logger = PrometheusStatLogger(
        config,
        engine_indexes=list(range(len(scenarios))),
    )
    logger.record(first_stats, None, engine_idx=0)
    for engine_index, (capacity, deferred) in enumerate(scenarios[1:], start=1):
        stats, _ = scheduler_stats(
            path / f"engine-{engine_index}",
            capacity=capacity,
            deferred=deferred,
        )
        logger.record(stats, None, engine_idx=engine_index)
    return generate_latest().decode()


def metric_value(
    text: str,
    name: str,
    *,
    engine: int,
    reason: str | None = None,
) -> float:
    for line in text.splitlines():
        if not line.startswith(name + "{"):
            continue
        if f'engine="{engine}"' not in line:
            continue
        if reason is not None and f'reason="{reason}"' not in line:
            continue
        return float(line.rsplit(" ", 1)[-1])
    raise AssertionError(f"metric not found: {name} engine={engine} reason={reason}")
