# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import contextlib
import ctypes
import json
import tempfile
from dataclasses import dataclass
from itertools import count
from math import prod
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import patch

import msgspec
import torch

from vllm import SamplingParams
from vllm.config import (
    AttentionConfig,
    CacheConfig,
    DeviceConfig,
    KVTransferConfig,
    ModelConfig,
    SchedulerConfig,
    VllmConfig,
    set_current_vllm_config,
)
from vllm.distributed.kv_transfer.kv_connector.v1.base import KVConnectorRole
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake import (
    mooncake_connector as mooncake,
)
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.mooncake_connector import (
    MooncakeConnector,
    MooncakeConnectorMetadata,
    PullReqMeta,
)
from vllm.v1.attention.backends.registry import MambaAttentionBackendEnum
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheConfig,
    KVCacheGroupSpec,
    MLAAttentionSpec,
    MambaSpec,
    SlidingWindowMLASpec,
)
from vllm.v1.outputs import ModelRunnerOutput
from vllm.v1.request import Request
from vllm.v1.structured_output import StructuredOutputManager


EOS_TOKEN_ID = 50256
_request_ids = count(1)
_none_hash_initialized = False
_model_dir: str | None = None


def local_model_dir() -> str:
    global _model_dir
    if _model_dir is None:
        directory = Path(tempfile.mkdtemp(prefix="vllm-config-"))
        (directory / "config.json").write_text(
            json.dumps(
                {
                    "architectures": ["OPTForCausalLM"],
                    "model_type": "opt",
                    "hidden_size": 16,
                    "ffn_dim": 32,
                    "num_attention_heads": 2,
                    "num_hidden_layers": 2,
                    "vocab_size": 128,
                    "max_position_embeddings": 10000,
                    "word_embed_proj_dim": 16,
                }
            )
        )
        _model_dir = str(directory)
    return _model_dir


def create_vllm_config(
    *,
    logical_block_size: int,
    connector: str,
    role: str,
    max_num_batched_tokens: int = 64,
) -> VllmConfig:
    model_config = ModelConfig(
        model=local_model_dir(),
        trust_remote_code=True,
        dtype="float16",
        seed=42,
        hf_overrides={},
    )
    scheduler_config = SchedulerConfig(
        max_num_seqs=16,
        max_num_batched_tokens=max_num_batched_tokens,
        max_model_len=10000,
        enable_chunked_prefill=True,
        is_encoder_decoder=model_config.is_encoder_decoder,
        disable_hybrid_kv_cache_manager=False,
    )
    cache_config = CacheConfig(
        block_size=logical_block_size,
        gpu_memory_utilization=0.9,
        cache_dtype="auto",
        enable_prefix_caching=True,
    )
    kv_transfer_config = KVTransferConfig(
        kv_connector=connector,
        kv_role=role,
        kv_load_failure_policy="fail",
    )
    return VllmConfig(
        scheduler_config=scheduler_config,
        model_config=model_config,
        cache_config=cache_config,
        kv_transfer_config=kv_transfer_config,
        device_config=DeviceConfig("cpu"),
        attention_config=AttentionConfig(),
    )


def create_scheduler(
    vllm_config: VllmConfig,
    *,
    num_blocks: int,
    kv_cache_config: KVCacheConfig,
) -> Scheduler:
    vllm_config.cache_config.num_gpu_blocks = num_blocks
    return Scheduler(
        vllm_config=vllm_config,
        kv_cache_config=kv_cache_config,
        log_stats=True,
        structured_output_manager=StructuredOutputManager(vllm_config),
        block_size=vllm_config.cache_config.block_size,
    )


def create_request(
    *,
    request_id: int | None = None,
    num_tokens: int,
    common_prefix_len: int = 0,
    max_tokens: int = 16,
    do_remote_decode: bool = False,
    do_remote_prefill: bool = False,
    block_size: int = 16,
    hash_fn: Callable = sha256,
) -> Request:
    assert num_tokens >= common_prefix_len >= 0
    request_id = next(_request_ids) if request_id is None else request_id
    global _none_hash_initialized
    if not _none_hash_initialized:
        init_none_hash(hash_fn)
        _none_hash_initialized = True

    common_prefix = [1] * common_prefix_len
    suffix = [index * request_id for index in range(num_tokens - common_prefix_len)]
    request = Request(
        request_id=f"request-{request_id}",
        prompt_token_ids=common_prefix + suffix,
        sampling_params=SamplingParams(max_tokens=max_tokens),
        pooling_params=None,
        mm_features=None,
        block_hasher=get_request_block_hasher(block_size, hash_fn),
    )
    if do_remote_decode:
        request.kv_transfer_params = {
            "do_remote_prefill": False,
            "do_remote_decode": True,
            "transfer_id": f"transfer-{request_id}",
        }
    elif do_remote_prefill:
        request.kv_transfer_params = {
            "do_remote_prefill": True,
            "do_remote_decode": False,
            "transfer_id": f"transfer-{request_id}",
            "remote_engine_id": "producer-engine",
            "remote_bootstrap_addr": "http://unused",
        }
    return request


def create_model_runner_output(
    requests: list[Request], *, use_eos: bool = False
) -> ModelRunnerOutput:
    request_ids = [request.request_id for request in requests]
    token = EOS_TOKEN_ID if use_eos else 0
    return ModelRunnerOutput(
        req_ids=request_ids,
        req_id_to_index={request_id: index for index, request_id in enumerate(request_ids)},
        sampled_token_ids=[[token] for _ in request_ids],
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=None,
    )


class GDNLayoutBackend:
    @staticmethod
    def get_name() -> str:
        return "GDN_LAYOUT_TEST"

    @staticmethod
    def get_kv_cache_shape(*_args, **_kwargs):
        raise NotImplementedError("GDN cache shape is described by MambaSpec")


class AttentionLayoutBackend:
    @staticmethod
    def get_name() -> str:
        return "ATTENTION_LAYOUT_TEST"

    @staticmethod
    def get_kv_cache_shape(
        num_blocks: int,
        block_size: int,
        num_kv_heads: int,
        head_size: int,
    ) -> tuple[int, ...]:
        return (num_blocks, 2, num_kv_heads, block_size, head_size)


@dataclass
class MemoryTransport:
    fail_registration: bool = False
    fail_transfer: bool = False

    def __post_init__(self) -> None:
        self.regions: list[tuple[int, int]] = []
        self.transfers: list[tuple[int, int, int]] = []

    def register(self, addresses, lengths) -> int:
        if self.fail_registration:
            return 1
        new_regions = [
            (int(address), int(length))
            for address, length in zip(addresses, lengths, strict=True)
        ]
        for index, (start, size) in enumerate(new_regions):
            end = start + size
            if any(
                start < other_start + other_size and other_start < end
                for other_start, other_size in new_regions[index + 1 :]
            ):
                return 3
        self.regions.extend(new_regions)
        return 0

    def _contains(self, address: int, length: int) -> bool:
        end = address + length
        return any(start <= address and end <= start + size for start, size in self.regions)

    def copy(self, sources, destinations, lengths) -> int:
        if self.fail_transfer:
            return 1
        triples = list(zip(sources, destinations, lengths, strict=True))
        if not all(
            self._contains(int(source), int(length))
            and self._contains(int(destination), int(length))
            for source, destination, length in triples
        ):
            return 2
        for source, destination, length in triples:
            ctypes.memmove(int(destination), int(source), int(length))
            self.transfers.append((int(source), int(destination), int(length)))
        return 0


class InMemoryMooncakeEngine:
    def __init__(self, transport: MemoryTransport):
        self.transport = transport

    def initialize(self, *_args, **_kwargs) -> int:
        return 0

    def get_rpc_port(self) -> int:
        return 12345

    def batch_register_memory(self, addresses, lengths) -> int:
        return self.transport.register(addresses, lengths)

    def batch_transfer_sync_write(self, _target, sources, destinations, lengths) -> int:
        return self.transport.copy(sources, destinations, lengths)


class ResponseSocket:
    def __init__(self, responses: list[bytes]):
        self.responses = responses

    async def send_multipart(self, message) -> None:
        _identity, payload = message
        self.responses.append(payload)


class LoopbackDealerSocket:
    def __init__(self, producer: mooncake.MooncakeConnectorWorker):
        self.producer = producer
        self.responses: list[bytes] = []

    def setsockopt(self, *_args) -> None:
        return None

    async def send(self, payload: bytes) -> None:
        metadata = msgspec.msgpack.decode(payload, type=mooncake.MooncakeXferMetadata)
        future = asyncio.run_coroutine_threadsafe(
            self.producer.send_kv_to_decode(
                b"in-memory-consumer",
                ResponseSocket(self.responses),
                metadata,
            ),
            self.producer.sender_loop,
        )
        await asyncio.wrap_future(future)

    async def recv(self) -> bytes:
        return self.responses.pop(0)


class SocketContext:
    def __init__(self, socket):
        self.socket = socket

    def __enter__(self):
        return self.socket

    def __exit__(self, *_args):
        return False


class SuccessfulResponse:
    def raise_for_status(self) -> None:
        return None


class SuccessfulAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *_args, **_kwargs):
        return SuccessfulResponse()


async def ready_without_network(_worker, ready_event) -> None:
    ready_event.set()


@contextlib.contextmanager
def patched_worker_runtime(
    transport: MemoryTransport,
    *,
    kernel_block_size: int,
    hybrid_backends: bool = True,
):
    engine_factory = lambda: InMemoryMooncakeEngine(transport)
    pp_group = SimpleNamespace(rank_in_group=0)
    first_backend = GDNLayoutBackend if hybrid_backends else AttentionLayoutBackend
    all_backends = (
        [GDNLayoutBackend, AttentionLayoutBackend]
        if hybrid_backends
        else [AttentionLayoutBackend]
    )
    with (
        patch.object(mooncake, "TransferEngine", side_effect=engine_factory),
        patch.object(mooncake, "get_ip", return_value="127.0.0.1"),
        patch.object(mooncake, "get_tensor_model_parallel_rank", return_value=0),
        patch.object(
            mooncake, "get_tensor_model_parallel_world_size", return_value=1
        ),
        patch.object(mooncake, "get_pp_group", return_value=pp_group),
        patch.object(mooncake, "should_launch_bootstrap_server", return_value=False),
        patch.object(
            mooncake,
            "get_current_attn_backend",
            return_value=first_backend,
            create=True,
        ),
        patch.object(
            mooncake,
            "get_current_attn_backends",
            return_value=all_backends,
        ),
        patch.object(
            mooncake,
            "select_common_block_size",
            return_value=kernel_block_size,
        ),
        patch.object(mooncake, "get_kv_cache_layout", return_value="HND"),
        patch.object(mooncake.current_platform, "set_device", return_value=None),
        patch.object(torch.accelerator, "current_device_index", return_value=0),
        patch.object(mooncake.httpx, "AsyncClient", SuccessfulAsyncClient),
        patch.object(
            mooncake.MooncakeConnectorWorker,
            "_mooncake_sender_listener",
            ready_without_network,
        ),
    ):
        yield


def make_vllm_config(
    role: str,
    *,
    logical_block_size: int,
    connector: str = "MooncakeConnector",
):
    config = create_vllm_config(
        logical_block_size=logical_block_size,
        connector=connector,
        role=role,
    )
    config.kv_transfer_config.engine_id = f"{role}-engine"
    config.kv_transfer_config.kv_connector_extra_config["num_workers"] = 1
    return config


def make_gdn_spec(block_size: int) -> MambaSpec:
    return MambaSpec(
        block_size=block_size,
        shapes=((6, 3), (1, 2, 2)),
        dtypes=(torch.float16, torch.float16),
        mamba_type=MambaAttentionBackendEnum.GDN_ATTN,
    )


def make_hybrid_config(
    *,
    logical_block_size: int = 16,
    num_blocks: int = 10,
    attention_kind: str = "full",
) -> KVCacheConfig:
    if attention_kind == "full":
        attention_spec = FullAttentionSpec(
            block_size=logical_block_size,
            num_kv_heads=1,
            head_size=2,
            dtype=torch.uint8,
        )
    elif attention_kind == "mla":
        attention_spec = MLAAttentionSpec(
            block_size=logical_block_size,
            num_kv_heads=1,
            head_size=2,
            dtype=torch.uint8,
            page_size_padded=4 * logical_block_size,
        )
    elif attention_kind == "sliding_mla":
        attention_spec = SlidingWindowMLASpec(
            block_size=logical_block_size,
            num_kv_heads=1,
            head_size=2,
            dtype=torch.uint8,
            page_size_padded=4 * logical_block_size,
            sliding_window=4 * logical_block_size,
        )
    else:
        raise ValueError(attention_kind)
    return KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(["model.layers.0.self_attn"], attention_spec),
            KVCacheGroupSpec(["model.layers.1.linear_attn"], make_gdn_spec(logical_block_size)),
        ],
    )


def make_pure_attention_config(
    *, logical_block_size: int = 16, num_blocks: int = 10
) -> KVCacheConfig:
    return KVCacheConfig(
        num_blocks=num_blocks,
        kv_cache_tensors=[],
        kv_cache_groups=[
            KVCacheGroupSpec(
                ["model.layers.0.self_attn"],
                FullAttentionSpec(
                    block_size=logical_block_size,
                    num_kv_heads=1,
                    head_size=2,
                    dtype=torch.uint8,
                ),
            )
        ],
    )


def make_hybrid_caches(
    config: KVCacheConfig,
    *,
    physical_ratio: int = 1,
    attention_row_bytes: int | None = None,
):
    attention_spec = config.kv_cache_groups[0].kv_cache_spec
    logical_page_bytes = attention_spec.page_size_bytes
    row_bytes = attention_row_bytes or logical_page_bytes // physical_ratio
    attention = torch.zeros(
        (config.num_blocks * physical_ratio, row_bytes), dtype=torch.uint8
    )
    mamba_spec = config.kv_cache_groups[1].kv_cache_spec
    assert isinstance(mamba_spec, MambaSpec)
    mamba_cache = make_mamba_cache(mamba_spec, config.num_blocks)
    return {
        "model.layers.0.self_attn": attention,
        "model.layers.1.linear_attn": mamba_cache,
    }


def make_mamba_cache(
    spec: MambaSpec,
    num_blocks: int,
    *,
    backing: torch.Tensor | None = None,
    page_stride_bytes: int | None = None,
) -> tuple[torch.Tensor, ...]:
    """Build production-shaped state views over one page-strided allocation."""
    page_stride_bytes = page_stride_bytes or spec.page_size_bytes
    assert page_stride_bytes >= spec.page_size_bytes
    if backing is None:
        backing = torch.zeros(num_blocks * page_stride_bytes, dtype=torch.uint8)
    assert backing.dtype == torch.uint8
    assert backing.numel() >= num_blocks * page_stride_bytes
    state_tensors: list[torch.Tensor] = []
    storage_offset_bytes = 0
    for shape, dtype in zip(spec.shapes, spec.dtypes, strict=True):
        element_size = torch.empty((), dtype=dtype).element_size()
        assert page_stride_bytes % element_size == 0
        assert storage_offset_bytes % element_size == 0
        natural_stride = torch.empty(shape, dtype=dtype).stride()
        state_tensors.append(
            torch.as_strided(
                backing.view(dtype),
                size=(num_blocks, *shape),
                stride=(page_stride_bytes // element_size, *natural_stride),
                storage_offset=storage_offset_bytes // element_size,
            )
        )
        storage_offset_bytes += prod(shape) * element_size
    assert storage_offset_bytes <= spec.page_size_bytes
    return tuple(state_tensors)


def make_cross_group_shared_caches(config: KVCacheConfig):
    """Build full-attention and GDN views sharing one HMA-style allocation."""
    attention_spec = config.kv_cache_groups[0].kv_cache_spec
    mamba_spec = config.kv_cache_groups[1].kv_cache_spec
    assert isinstance(attention_spec, FullAttentionSpec)
    assert isinstance(mamba_spec, MambaSpec)
    page_stride_bytes = max(
        attention_spec.page_size_bytes,
        mamba_spec.page_size_bytes,
    )
    backing = torch.zeros(
        config.num_blocks * page_stride_bytes,
        dtype=torch.uint8,
    )
    attention = torch.as_strided(
        backing,
        size=(config.num_blocks, attention_spec.page_size_bytes),
        stride=(page_stride_bytes, 1),
    )
    mamba_cache = make_mamba_cache(
        mamba_spec,
        config.num_blocks,
        backing=backing,
        page_stride_bytes=page_stride_bytes,
    )
    assert attention.data_ptr() == mamba_cache[0].data_ptr()
    return {
        "model.layers.0.self_attn": attention,
        "model.layers.1.linear_attn": mamba_cache,
    }


def mamba_storage_bytes(cache: tuple[torch.Tensor, ...]) -> torch.Tensor:
    """Expose the complete shared allocation for end-state comparisons."""
    storage = cache[0].untyped_storage()
    return torch.empty(0, dtype=torch.uint8).set_(
        storage,
        0,
        (storage.nbytes(),),
        (1,),
    )


def make_pure_attention_caches(
    config: KVCacheConfig,
    *,
    physical_ratio: int = 1,
):
    attention_spec = config.kv_cache_groups[0].kv_cache_spec
    row_bytes = attention_spec.page_size_bytes // physical_ratio
    return {
        "model.layers.0.self_attn": torch.zeros(
            (config.num_blocks * physical_ratio, row_bytes), dtype=torch.uint8
        )
    }


def make_worker_connector(
    role: str,
    config: KVCacheConfig,
    *,
    logical_block_size: int,
) -> MooncakeConnector:
    vllm_config = make_vllm_config(role, logical_block_size=logical_block_size)
    with set_current_vllm_config(vllm_config):
        return MooncakeConnector(vllm_config, KVConnectorRole.WORKER, config)


async def transfer_once(
    producer: MooncakeConnector,
    consumer: MooncakeConnector,
    *,
    local_block_ids: list[list[int]],
    remote_block_ids: list[list[int]],
    transfer_id: str = "transfer",
) -> tuple[set[str] | None, set[str] | None]:
    producer_worker = producer.connector_worker
    consumer_worker = consumer.connector_worker
    assert producer_worker is not None and consumer_worker is not None

    announced = MooncakeConnectorMetadata()
    announced.add_new_req(
        request_id="producer-request",
        local_block_ids=[],
        kv_transfer_params={"transfer_id": transfer_id},
        load_remote_cache=False,
    )
    await producer_worker.record_send_reqs(announced)
    ready = MooncakeConnectorMetadata()
    ready.add_new_req(
        request_id="producer-request",
        local_block_ids=local_block_ids,
        kv_transfer_params={"transfer_id": transfer_id},
        load_remote_cache=False,
    )
    await producer_worker.record_send_reqs(ready)
    pull = PullReqMeta(
        d_req_id="decoder-request",
        transfer_id=transfer_id,
        local_block_ids=remote_block_ids,
        remote_engine_id="producer-engine",
        remote_bootstrap_addr="http://unused",
        pull_tasks_count=1,
    )

    dealer = LoopbackDealerSocket(producer_worker)
    with patch.object(
        mooncake,
        "make_zmq_socket",
        return_value=SocketContext(dealer),
    ):
        await consumer_worker.receive_kv_from_single_worker(
            "loopback", {"decoder-request": pull}
        )

    return consumer.get_finished(set())


def shutdown_connectors(*connectors: MooncakeConnector) -> None:
    for connector in connectors:
        worker = connector.connector_worker
        if worker is not None:
            worker.shutdown()
            worker.shutdown = lambda: None
            connector.connector_worker = None
