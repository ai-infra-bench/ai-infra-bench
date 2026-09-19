#!/usr/bin/env python3
"""Construct valid production scheduler inputs; contains no scoring policy."""

from __future__ import annotations

import copy
from concurrent.futures import Future
import gc
import json
import sys
import tempfile
import types
from pathlib import Path

import torch

MODEL_CONFIG = {
    "_name_or_path": "facebook/opt-125m",
    "architectures": ["OPTForCausalLM"],
    "bos_token_id": 2,
    "eos_token_id": 2,
    "hidden_size": 768,
    "max_position_embeddings": 2048,
    "model_type": "opt",
    "torch_dtype": "float16",
    "num_attention_heads": 12,
    "num_hidden_layers": 12,
    "pad_token_id": 1,
    "vocab_size": 50272,
}


_CONNECTOR_MODULE = "_ai_infra_remote_kv_verifier"
_HASH_INITIALIZED = False
_CANDIDATE_LOADED = False


def load_candidate() -> None:
    """Import candidate code only after the trusted parent has forked."""
    global _CANDIDATE_LOADED
    if _CANDIDATE_LOADED:
        return
    sys.path.insert(0, "/app")

    from vllm.config import (
        CacheConfig,
        KVTransferConfig,
        ModelConfig,
        ParallelConfig,
        SchedulerConfig,
        VllmConfig,
    )
    from vllm.distributed.kv_transfer.kv_connector.v1 import (
        KVConnectorBase_V1,
        KVConnectorRole,
    )
    from vllm.sampling_params import SamplingParams, StructuredOutputsParams
    from vllm.utils.hashing import sha256
    from vllm.v1.core.kv_cache_utils import (
        get_request_block_hasher,
        init_none_hash,
    )
    from vllm.v1.core.sched.scheduler import Scheduler
    from vllm.v1.kv_cache_interface import (
        FullAttentionSpec,
        KVCacheConfig,
        KVCacheGroupSpec,
    )
    from vllm.v1.outputs import (
        EMPTY_MODEL_RUNNER_OUTPUT,
        KVConnectorOutput,
        ModelRunnerOutput,
    )
    from vllm.v1.request import Request, RequestStatus
    from vllm.v1.structured_output import StructuredOutputManager

    globals().update(
        {
            name: value
            for name, value in locals().items()
            if name not in {"name", "value"}
        }
    )

    class VerifierKVConnector(KVConnectorBase_V1):
        """Minimal asynchronous receive connector owned by the verifier."""

        def __init__(self, vllm_config, role, kv_cache_config=None) -> None:
            super().__init__(vllm_config, role, kv_cache_config)

        def get_num_new_matched_tokens(self, request, num_computed_tokens):
            return 8, True

        def update_state_after_alloc(self, request, blocks, num_external_tokens):
            return None

        def build_connector_meta(self, scheduler_output):
            return None

        def start_load_kv(self, forward_context, **kwargs):
            return None

        def wait_for_layer_load(self, layer_name):
            return None

        def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
            return None

        def wait_for_save(self):
            return None

    module = types.ModuleType(_CONNECTOR_MODULE)
    module.VerifierKVConnector = VerifierKVConnector
    sys.modules[_CONNECTOR_MODULE] = module
    _CANDIDATE_LOADED = True


def create_requests(
    request_count: int,
    *,
    token_counts: list[int] | None = None,
    request_ids: list[str] | None = None,
    max_tokens: int = 16,
) -> list[Request]:
    global _HASH_INITIALIZED
    if not _HASH_INITIALIZED:
        init_none_hash(sha256)
        _HASH_INITIALIZED = True
    block_hasher = get_request_block_hasher(16, sha256)
    sampling_params = SamplingParams(max_tokens=max_tokens, ignore_eos=True)
    sampling_params.update_from_generation_config({}, 50256)
    if token_counts is None:
        token_counts = [10] * request_count
    if request_ids is None:
        request_ids = [str(index) for index in range(request_count)]
    assert len(token_counts) == request_count
    assert len(request_ids) == request_count
    return [
        Request(
            request_id=request_ids[index],
            prompt_token_ids=[index] * token_counts[index],
            sampling_params=sampling_params,
            pooling_params=None,
            block_hasher=block_hasher,
        )
        for index in range(request_count)
    ]


def create_scheduler(
    model_dir: str,
    request_count: int,
    *,
    max_num_batched_tokens: int | None = None,
    use_connector: bool = True,
) -> Scheduler:
    model_config = ModelConfig(
        model=model_dir,
        trust_remote_code=False,
        dtype="float16",
        seed=42,
        skip_tokenizer_init=True,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=request_count,
        max_num_batched_tokens=(
            max_num_batched_tokens
            if max_num_batched_tokens is not None
            else max(8192, request_count * 16)
        ),
        max_model_len=2048,
        enable_chunked_prefill=True,
        is_encoder_decoder=model_config.is_encoder_decoder,
    )
    cache_config = CacheConfig(
        block_size=16,
        gpu_memory_utilization=0.9,
        cache_dtype="auto",
        enable_prefix_caching=False,
    )
    cache_config.num_gpu_blocks = 10000
    transfer_config = KVTransferConfig(
        kv_connector="VerifierKVConnector",
        kv_connector_module_path=_CONNECTOR_MODULE,
        kv_role="kv_both",
    )
    vllm_config = VllmConfig(
        scheduler_config=scheduler_config,
        model_config=model_config,
        cache_config=cache_config,
        parallel_config=ParallelConfig(),
        kv_transfer_config=transfer_config if use_connector else None,
    )
    kv_cache_config = KVCacheConfig(
        num_blocks=10000,
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
    return Scheduler(
        vllm_config=vllm_config,
        kv_cache_config=kv_cache_config,
        block_size=16,
        log_stats=False,
        structured_output_manager=StructuredOutputManager(vllm_config),
    )


def create_blocked_scheduler(model_dir: str, request_count: int):
    scheduler = create_scheduler(model_dir, request_count)
    requests = create_requests(request_count)
    for request in requests:
        scheduler.add_request(request)
    output = scheduler.schedule()
    assert not output.scheduled_new_reqs
    assert all(r.status == RequestStatus.WAITING_FOR_REMOTE_KVS for r in requests)
    assert scheduler.get_request_counts() == (0, request_count)
    return scheduler, requests, output
