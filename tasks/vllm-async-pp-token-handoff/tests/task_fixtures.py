#!/usr/bin/env python3
"""Task-owned scheduler/request fixtures for the async-PP verifier.

Previously the verifier imported ``tests.v1.core.utils`` from the candidate
work tree (``/workspace/repo/tests``), so the candidate could rewrite the very
fixtures used to judge it. These builders live in the task-owned, root-staged
``/tests`` tree instead and construct the fixtures from vLLM's *public*
configuration classes only.

This does not pretend to be a trust boundary by itself: this module still runs
inside an untrusted worker that imports the candidate ``vllm``. What it removes
is the candidate's ability to supply the fixture *definitions* while presenting
them as the task's own.
"""

from __future__ import annotations

import torch

from vllm.config import (
    CacheConfig,
    ModelConfig,
    ParallelConfig,
    SchedulerConfig,
    VllmConfig,
)
from vllm.sampling_params import SamplingParams
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.request import Request
from vllm.v1.structured_output import StructuredOutputManager

BLOCK_SIZE = 16
NUM_BLOCKS = 4096


def build_scheduler(
    model: str,
    *,
    async_scheduling: bool,
    pipeline_parallel_size: int,
    max_model_len: int = 8192,
    max_num_seqs: int = 16,
    max_num_batched_tokens: int = 8192,
    block_size: int = BLOCK_SIZE,
    num_blocks: int = NUM_BLOCKS,
    skip_tokenizer_init: bool = True,
    long_prefill_token_threshold: int = 0,
):
    """Construct a production Scheduler/AsyncScheduler over public config classes.

    Mirrors the reference construction the candidate's own test utility performs,
    including the fields that have no defaults (``is_encoder_decoder``) and the
    positional/keyword arguments ``Scheduler.__init__`` actually requires
    (``kv_cache_config``, ``block_size``, ``structured_output_manager``). Passing
    ``None`` for those raises, which is a fixture bug rather than a candidate
    failure -- so they are built properly here.
    """
    model_config = ModelConfig(
        model=model,
        trust_remote_code=False,
        dtype="float16",
        seed=42,
        skip_tokenizer_init=skip_tokenizer_init,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=max_num_seqs,
        max_num_batched_tokens=max_num_batched_tokens,
        max_model_len=max_model_len,
        enable_chunked_prefill=True,
        long_prefill_token_threshold=long_prefill_token_threshold,
        async_scheduling=async_scheduling,
        # No default in the candidate base: omitting it fails pydantic validation.
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(
        block_size=block_size,
        gpu_memory_utilization=0.9,
        swap_space=0,
        cache_dtype="auto",
        enable_prefix_caching=False,
    )
    vllm_config = VllmConfig(
        scheduler_config=scheduler_config,
        model_config=model_config,
        cache_config=cache_config,
        parallel_config=ParallelConfig(
            pipeline_parallel_size=pipeline_parallel_size
        ),
    )
    kv_cache_config = KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["layer"],
                FullAttentionSpec(
                    block_size=block_size,
                    num_kv_heads=1,
                    head_size=1,
                    dtype=torch.float32,
                ),
            )
        ],
    )
    cache_config.num_gpu_blocks = num_blocks
    scheduler_cls = vllm_config.scheduler_config.get_scheduler_cls()
    return scheduler_cls(
        vllm_config=vllm_config,
        kv_cache_config=kv_cache_config,
        block_size=block_size,
        log_stats=False,
        structured_output_manager=StructuredOutputManager(vllm_config),
    )


def build_requests(num_requests: int, num_tokens: int) -> list:
    """Deterministic public-API Request objects."""
    out = []
    for i in range(num_requests):
        out.append(
            Request(
                request_id=f"async-pp-{i}",
                prompt_token_ids=list(range(num_tokens)),
                sampling_params=SamplingParams(max_tokens=16),
                pooling_params=None,
                eos_token_id=None,
            )
        )
    return out


# Compatibility aliases: same call shape the verifier previously used against
# the candidate's tests.v1.core.utils, so switching the source of truth does not
# change the call sites.
def create_scheduler(
    model: str,
    *,
    async_scheduling: bool = False,
    pipeline_parallel_size: int = 1,
    skip_tokenizer_init: bool = True,  # noqa: ARG001 - always public-init here
    max_model_len: int = 8192,
    **_ignored,
):
    return build_scheduler(
        model,
        async_scheduling=async_scheduling,
        pipeline_parallel_size=pipeline_parallel_size,
        max_model_len=max_model_len,
    )


def create_requests(num_requests: int, num_tokens: int = 8, **_ignored) -> list:
    return build_requests(num_requests, num_tokens)
