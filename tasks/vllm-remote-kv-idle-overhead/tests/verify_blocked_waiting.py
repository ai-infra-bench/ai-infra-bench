#!/usr/bin/env python3
"""Behavioral and deterministic-work contract for remote-KV waiting."""

from __future__ import annotations

import copy
import json
import statistics
import sys
import tempfile
import time
import types
from pathlib import Path

import torch

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
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.outputs import EMPTY_MODEL_RUNNER_OUTPUT, KVConnectorOutput
from vllm.v1.request import Request, RequestStatus
from vllm.v1.structured_output import StructuredOutputManager


REQUEST_COUNT = 24
IDLE_ROUNDS = 200
MODEL_CONFIG = {
    "_name_or_path": "facebook/opt-125m",
    "architectures": ["OPTForCausalLM"],
    "bos_token_id": 2,
    "eos_token_id": 2,
    "hidden_size": 768,
    "max_position_embeddings": 2048,
    "model_type": "opt",
    "num_attention_heads": 12,
    "num_hidden_layers": 12,
    "pad_token_id": 1,
    "vocab_size": 50272,
}


class VerifierKVConnector(KVConnectorBase_V1):
    """Minimal asynchronous receive connector owned by the hidden verifier."""

    def __init__(
        self,
        vllm_config: VllmConfig,
        role: KVConnectorRole,
        kv_cache_config: KVCacheConfig | None = None,
    ) -> None:
        super().__init__(vllm_config, role, kv_cache_config)

    def get_num_new_matched_tokens(
        self, request: Request, num_computed_tokens: int
    ) -> tuple[int | None, bool]:
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


_CONNECTOR_MODULE = "_ai_infra_remote_kv_verifier"
_module = types.ModuleType(_CONNECTOR_MODULE)
_module.VerifierKVConnector = VerifierKVConnector
sys.modules[_CONNECTOR_MODULE] = _module

_HASH_INITIALIZED = False


def create_requests(request_count: int) -> list[Request]:
    global _HASH_INITIALIZED
    if not _HASH_INITIALIZED:
        init_none_hash(sha256)
        _HASH_INITIALIZED = True
    block_hasher = get_request_block_hasher(16, sha256)
    sampling_params = SamplingParams(max_tokens=16)
    sampling_params.update_from_generation_config({}, 50256)
    return [
        Request(
            request_id=str(index),
            prompt_token_ids=[index] * 10,
            sampling_params=sampling_params,
            pooling_params=None,
            block_hasher=block_hasher,
        )
        for index in range(request_count)
    ]


def create_scheduler(model_dir: str, request_count: int) -> Scheduler:
    model_config = ModelConfig(
        model=model_dir,
        trust_remote_code=False,
        dtype="float16",
        seed=42,
        skip_tokenizer_init=True,
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=request_count,
        max_num_batched_tokens=max(8192, request_count * 16),
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
        kv_transfer_config=transfer_config,
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


def measure_idle(model_dir: str, request_count: int) -> float:
    scheduler, _, _ = create_blocked_scheduler(model_dir, request_count)
    scheduler.schedule()
    samples = []
    for _ in range(5):
        started = time.perf_counter_ns()
        for _ in range(IDLE_ROUNDS):
            output = scheduler.schedule()
            assert not output.scheduled_new_reqs
        samples.append(time.perf_counter_ns() - started)
    assert scheduler.get_request_counts() == (0, request_count)
    return statistics.median(samples) / IDLE_ROUNDS


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="remote-kv-model-") as tmp:
        model_dir = Path(tmp)
        (model_dir / "config.json").write_text(json.dumps(MODEL_CONFIG))

        small_ns = measure_idle(str(model_dir), REQUEST_COUNT)
        large_count = REQUEST_COUNT * 16
        large_ns = measure_idle(str(model_dir), large_count)
        ratio = large_ns / max(small_ns, 1.0)
        if ratio >= 6.0:
            raise AssertionError(
                "idle remote-KV tick still scales with blocked population: "
                f"small={small_ns:.0f}ns large={large_ns:.0f}ns ratio={ratio:.2f}"
            )

        scheduler, requests, output = create_blocked_scheduler(
            str(model_dir), REQUEST_COUNT
        )
        ready_ids = {requests[i].request_id for i in (2, 7, 13)}
        finished = copy.deepcopy(EMPTY_MODEL_RUNNER_OUTPUT)
        finished.kv_connector_output = KVConnectorOutput(finished_recving=ready_ids)
        scheduler.update_from_output(output, finished)
        resumed = scheduler.schedule()
        resumed_ids = [request.req_id for request in resumed.scheduled_new_reqs]
        expected_ids = [r.request_id for r in requests if r.request_id in ready_ids]
        if resumed_ids != expected_ids:
            raise AssertionError(f"completion promotion/order changed: {resumed_ids}")
        running, waiting = scheduler.get_request_counts()
        assert running == len(ready_ids)
        assert waiting == REQUEST_COUNT - len(ready_ids)

        victim = requests[-1]
        scheduler.finish_requests(victim.request_id, RequestStatus.FINISHED_ABORTED)
        assert victim.status == RequestStatus.FINISHED_ABORTED

        print(
            json.dumps(
                {
                "small_requests": REQUEST_COUNT,
                "large_requests": large_count,
                "idle_rounds": IDLE_ROUNDS,
                "small_tick_ns": small_ns,
                "large_tick_ns": large_ns,
                "scaling_ratio": ratio,
                "resumed": resumed_ids,
            },
                sort_keys=True,
            )
        )
        print("PASS: remote-KV waiting idle overhead is bounded")


if __name__ == "__main__":
    main()
