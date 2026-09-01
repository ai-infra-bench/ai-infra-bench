from __future__ import annotations

import json
import tempfile
from pathlib import Path

import torch
from prometheus_client import generate_latest

from vllm.config import CacheConfig, ModelConfig, SchedulerConfig, VllmConfig
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


def scheduler() -> tuple[Scheduler, VllmConfig]:
    model_dir = Path(tempfile.mkdtemp(prefix="waiting-metrics-model-"))
    (model_dir / "config.json").write_text(
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
            }
        )
    )
    model = ModelConfig(
        model=str(model_dir),
        dtype="float16",
        skip_tokenizer_init=True,
    )
    config = VllmConfig(
        model_config=model,
        scheduler_config=SchedulerConfig(
            max_num_seqs=2,
            max_num_batched_tokens=100,
            max_model_len=128,
            enable_chunked_prefill=True,
            async_scheduling=False,
            is_encoder_decoder=model.is_encoder_decoder,
        ),
        cache_config=CacheConfig(
            block_size=16,
            gpu_memory_utilization=0.9,
            cache_dtype="auto",
        ),
    )
    config.cache_config.num_gpu_blocks = 64
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
    return (
        Scheduler(
            vllm_config=config,
            kv_cache_config=kv_config,
            block_size=16,
            log_stats=True,
            structured_output_manager=StructuredOutputManager(config),
        ),
        config,
    )


def make_request(name: str, *, deferred: bool) -> Request:
    params = SamplingParams(max_tokens=4)
    params.update_from_generation_config({}, 127)
    item = Request(
        request_id=name,
        prompt_token_ids=[1] * 50,
        sampling_params=params,
        pooling_params=None,
        block_hasher=get_request_block_hasher(16, sha256),
    )
    if deferred:
        item.status = RequestStatus.WAITING_FOR_REMOTE_KVS
    return item


def main() -> int:
    init_none_hash(sha256)
    queue, config = scheduler()
    for index in range(3):
        queue.add_request(make_request(f"capacity-{index}", deferred=False))
    for index in range(2):
        queue.add_request(make_request(f"deferred-{index}", deferred=True))
    output = queue.schedule()
    ids = list(output.num_scheduled_tokens)
    results = queue.update_from_output(
        output,
        ModelRunnerOutput(
            req_ids=ids,
            req_id_to_index={name: i for i, name in enumerate(ids)},
            sampled_token_ids=[[1]] * len(ids),
            logprobs=None,
            prompt_logprobs_dict={},
            pooler_output=[],
        ),
    )
    stats = results[0].scheduler_stats
    logger = PrometheusStatLogger(config)
    logger.record(stats, None)
    text = generate_latest().decode()
    selected = [
        line
        for line in text.splitlines()
        if line.startswith("vllm:num_requests_waiting")
    ]
    print("\n".join(selected))
    has_breakdown = any(
        line.startswith("vllm:num_requests_waiting_by_reason")
        for line in selected
    )
    print(f"waiting_reason_breakdown_present={has_breakdown}")
    return 0 if has_breakdown else 3


if __name__ == "__main__":
    raise SystemExit(main())
