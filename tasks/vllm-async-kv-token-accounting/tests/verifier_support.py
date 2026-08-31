"""Verifier-owned fixtures that exercise the public KV connector contract."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import torch

from vllm import SamplingParams
from vllm.config import (
    CacheConfig,
    DeviceConfig,
    KVTransferConfig,
    ModelConfig,
    SchedulerConfig,
    VllmConfig,
)
from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm.distributed.kv_transfer.kv_connector.v1.base import (
    KVConnectorBase_V1,
    KVConnectorMetadata,
    KVConnectorRole,
)
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
)
from vllm.v1.outputs import KVConnectorOutput, ModelRunnerOutput
from vllm.v1.request import Request
from vllm.v1.structured_output import StructuredOutputManager


@dataclass(frozen=True)
class TransferRecord:
    request_id: str
    matched_tokens: int
    block_ids: tuple[int, ...]


@dataclass
class AsyncTransferMetadata(KVConnectorMetadata):
    transfers: list[TransferRecord] = field(default_factory=list)


class AsyncMemoryConnector(KVConnectorBase_V1):
    """Hidden connector that performs an actual asynchronous memory copy."""

    def __init__(self, vllm_config, role, kv_cache_config=None):
        super().__init__(vllm_config, role, kv_cache_config)
        extra = vllm_config.kv_transfer_config.kv_connector_extra_config
        self._matches = {str(k): int(v) for k, v in extra.get("matches", {}).items()}
        self._sync_ids = set(extra.get("sync_request_ids", ()))
        self._delays = {
            str(k): float(v) / 1000 for k, v in extra.get("delays_ms", {}).items()
        }
        self._failures = {
            str(k): int(v) for k, v in extra.get("failure_block_index", {}).items()
        }
        self._pending: list[TransferRecord] = []
        self._request_blocks: dict[str, set[int]] = {}
        self._completed: set[str] = set()
        self._invalid_blocks: set[int] = set()
        self._checksums: dict[str, str] = {}
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    def get_num_new_matched_tokens(self, request, num_computed_tokens):
        matched = self._matches.get(request.request_id, 0)
        return matched, matched > 0 and request.request_id not in self._sync_ids

    def update_state_after_alloc(self, request, blocks, num_external_tokens):
        if num_external_tokens <= 0 or request.request_id in self._sync_ids:
            return
        groups = blocks.get_block_ids()
        block_ids = tuple(groups[0]) if groups else ()
        self._request_blocks[request.request_id] = set(block_ids)
        self._pending.append(
            TransferRecord(request.request_id, num_external_tokens, block_ids)
        )

    def build_connector_meta(self, scheduler_output):
        metadata = AsyncTransferMetadata(self._pending)
        self._pending = []
        return metadata

    def update_connector_output(self, connector_output):
        if connector_output.invalid_block_ids:
            invalid = connector_output.invalid_block_ids
            for request_id, block_ids in self._request_blocks.items():
                if block_ids & invalid:
                    self._matches[request_id] = 0
        return None

    def request_finished(self, request, block_ids):
        return False, None

    def take_events(self):
        return ()

    def start_load_kv(self, forward_context, **kwargs):
        metadata = self._get_connector_metadata()
        assert isinstance(metadata, AsyncTransferMetadata)
        for record in metadata.transfers:
            thread = threading.Thread(
                target=self._copy_transfer,
                args=(record,),
                name=f"async-kv-{record.request_id}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)
        self.clear_connector_metadata()

    def _copy_transfer(self, record):
        time.sleep(self._delays.get(record.request_id, 0.002))
        source = bytes(
            (record.matched_tokens + offset) % 251
            for offset in range(max(64, record.matched_tokens * 8))
        )
        copied = bytearray(len(source))
        copied[:] = source
        checksum = hashlib.sha256(copied).hexdigest()
        invalid = None
        failure_index = self._failures.get(record.request_id)
        if failure_index is not None and 0 <= failure_index < len(record.block_ids):
            invalid = record.block_ids[failure_index]
        with self._lock:
            self._checksums[record.request_id] = checksum
            if invalid is not None:
                self._invalid_blocks.add(invalid)
            self._completed.add(record.request_id)

    def get_finished(self, finished_req_ids):
        with self._lock:
            completed = set(self._completed)
            self._completed.clear()
        return None, completed or None

    def get_block_ids_with_load_errors(self):
        with self._lock:
            invalid = set(self._invalid_blocks)
            self._invalid_blocks.clear()
        return invalid

    def wait_for_layer_load(self, layer_name):
        return None

    def save_kv_layer(self, layer_name, kv_layer, attn_metadata, **kwargs):
        return None

    def wait_for_save(self):
        return None

    def shutdown(self):
        for thread in self._threads:
            thread.join(timeout=5)

    @property
    def completed_checksums(self):
        with self._lock:
            return dict(self._checksums)


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
                "vocab_size": 512,
                "max_position_embeddings": 1024,
                "word_embed_proj_dim": 64,
                "do_layer_norm_before": True,
                "torch_dtype": "float32",
            }
        )
    )
    return path


def make_config(
    model_dir: Path,
    *,
    block_size: int,
    matches: dict[str, int],
    sync_request_ids=(),
    delays_ms=None,
    failure_block_index=None,
):
    model_config = ModelConfig(
        model=str(model_dir),
        dtype="float32",
        skip_tokenizer_init=True,
        max_model_len=1024,
    )
    scheduler_config = SchedulerConfig(
        max_model_len=1024,
        is_encoder_decoder=False,
        max_num_seqs=32,
        max_num_batched_tokens=4096,
        enable_chunked_prefill=True,
        disable_hybrid_kv_cache_manager=True,
    )
    cache_config = CacheConfig(
        block_size=block_size,
        gpu_memory_utilization=0.5,
        swap_space=0,
        enable_prefix_caching=True,
    )
    cache_config.num_gpu_blocks = 512
    transfer_config = KVTransferConfig(
        kv_connector="AsyncMemoryConnector",
        kv_connector_module_path="verifier_support",
        kv_role="kv_both",
        kv_buffer_device="cpu",
        kv_load_failure_policy="recompute",
        kv_connector_extra_config={
            "matches": matches,
            "sync_request_ids": list(sync_request_ids),
            "delays_ms": delays_ms or {},
            "failure_block_index": failure_block_index or {},
        },
    )
    return VllmConfig(
        model_config=model_config,
        scheduler_config=scheduler_config,
        cache_config=cache_config,
        device_config=DeviceConfig("cpu"),
        kv_transfer_config=transfer_config,
    )


def make_cache_config(block_size: int, num_blocks: int = 512):
    return KVCacheConfig(
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


def make_scheduler(model_dir: Path, *, block_size=16, num_blocks=512, **plan):
    config = make_config(
        model_dir,
        block_size=block_size,
        matches=plan.pop("matches"),
        **plan,
    )
    config.cache_config.num_gpu_blocks = num_blocks
    cache_config = make_cache_config(block_size, num_blocks)
    scheduler = Scheduler(
        vllm_config=config,
        kv_cache_config=cache_config,
        structured_output_manager=StructuredOutputManager(config),
        block_size=block_size,
        log_stats=False,
    )
    return scheduler, config, cache_config


_hash_initialized = False


def make_request(request_id: str, token_ids: list[int], *, block_size: int):
    global _hash_initialized
    if not _hash_initialized:
        init_none_hash(sha256)
        _hash_initialized = True
    return Request(
        request_id=request_id,
        prompt_token_ids=list(token_ids),
        sampling_params=SamplingParams(max_tokens=1),
        pooling_params=None,
        block_hasher=get_request_block_hasher(block_size, sha256),
    )


def tokens(length: int, salt: int = 0):
    return [((salt + index * 17) % 509) + 1 for index in range(length)]


def empty_output(kv_output=None):
    return ModelRunnerOutput(
        req_ids=[],
        req_id_to_index={},
        sampled_token_ids=[],
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
        kv_connector_output=kv_output,
    )


def sampled_output(scheduler_output, kv_output=None):
    request_ids = list(scheduler_output.num_scheduled_tokens)
    return ModelRunnerOutput(
        req_ids=request_ids,
        req_id_to_index={req_id: index for index, req_id in enumerate(request_ids)},
        sampled_token_ids=[[7] for _ in request_ids],
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
        kv_connector_output=kv_output,
    )


def make_worker(config, cache_config):
    return KVConnectorFactory.create_connector(
        config,
        KVConnectorRole.WORKER,
        cache_config,
    )


def start_worker_transfer(worker, scheduler_output):
    worker.bind_connector_metadata(scheduler_output.kv_connector_metadata)
    worker.start_load_kv(None)


def wait_for_worker_output(worker, *, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _, finished = worker.get_finished(set())
        invalid = worker.get_block_ids_with_load_errors()
        if finished or invalid:
            return KVConnectorOutput(
                finished_recving=finished,
                invalid_block_ids=invalid,
            )
        time.sleep(0.005)
    raise TimeoutError("asynchronous connector did not finish")
