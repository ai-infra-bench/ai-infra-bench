"""Verifier-owned Mooncake receive-pipeline fixtures with real target buffers."""

from __future__ import annotations

import ctypes
import hashlib
import threading
from collections import Counter
from dataclasses import dataclass
from math import ceil, lcm

import torch

from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.store.coordinator import (
    ExternalCachedBlockPool,
    MooncakeStoreCoordinator,
)
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.store.data import (
    ChunkedTokenDatabase,
    KeyMetadata,
    LoadSpec,
    ReqMeta,
)
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.store.worker import (
    KVCacheStoreRecvingThread,
)
from vllm.v1.core.kv_cache_utils import BlockHash, BlockHashListWithBlockSize
from vllm.v1.kv_cache_interface import (
    FullAttentionSpec,
    KVCacheGroupSpec,
    MambaSpec,
    SlidingWindowSpec,
)


BLOCK_BYTES = 64
TARGET_MODEL_ID = "MiniMaxAI/MiniMax-M2.5"


@dataclass(frozen=True)
class GroupProfile:
    kind: str
    block_size: int
    window: int | None = None


@dataclass(frozen=True)
class ReceiveProfile:
    name: str
    groups: tuple[GroupProfile, ...]
    hash_block_size: int
    num_hashes: int
    max_length: int
    expected_hit_length: int
    use_eagle: bool


@dataclass(frozen=True)
class ReceiveResult:
    hit_length: int
    expected_keys: int
    loaded_keys: int
    verified_blocks: int
    requests: int
    groups: int


def full(block_size: int):
    return FullAttentionSpec(
        block_size=block_size,
        num_kv_heads=8,
        head_size=64,
        dtype=torch.float16,
    )


def swa(block_size: int, window: int):
    return SlidingWindowSpec(
        block_size=block_size,
        num_kv_heads=8,
        head_size=64,
        dtype=torch.float16,
        sliding_window=window,
    )


def mamba(block_size: int):
    return MambaSpec(
        block_size=block_size,
        shapes=((1, 1),),
        dtypes=(torch.float32,),
    )


def hashes(count: int):
    return [BlockHash(bytes([index + 1]) * 4) for index in range(count)]


def _spec(profile: GroupProfile):
    if profile.kind == "full":
        return full(profile.block_size)
    if profile.kind == "swa":
        assert profile.window is not None
        return swa(profile.block_size, profile.window)
    if profile.kind == "mamba":
        return mamba(profile.block_size)
    raise ValueError(profile.kind)


def _groups(profile: ReceiveProfile):
    return [
        KVCacheGroupSpec([f"group-{index}"], _spec(group))
        for index, group in enumerate(profile.groups)
    ]


def _coordinator(profile: ReceiveProfile):
    groups = _groups(profile)
    scheduler_block_size = lcm(*(g.block_size for g in profile.groups))
    return MooncakeStoreCoordinator(
        groups,
        scheduler_block_size=scheduler_block_size,
        hash_block_size=profile.hash_block_size,
        use_eagle=profile.use_eagle,
    )


def _group_hashes(block_hashes, hash_block_size, group_block_size):
    if hash_block_size == group_block_size:
        return list(block_hashes)
    return list(
        BlockHashListWithBlockSize(
            block_hashes,
            hash_block_size,
            group_block_size,
        )
    )


def _cached_pool(profile: ReceiveProfile, block_hashes):
    entries = set()
    for group_index, group in enumerate(profile.groups):
        for value in _group_hashes(
            block_hashes,
            profile.hash_block_size,
            group.block_size,
        ):
            entries.add((group_index, bytes(value)))
    return ExternalCachedBlockPool(entries)


def expected_mask(group: GroupProfile, hit_length: int):
    chunks = hit_length // group.block_size
    if group.kind == "full":
        return [True] * chunks
    if group.kind == "swa":
        assert group.window is not None
        tail = min(chunks, ceil((group.window - 1) / group.block_size))
        return [False] * (chunks - tail) + [True] * tail
    if group.kind == "mamba":
        return [False] * max(0, chunks - 1) + ([True] if chunks else [])
    raise ValueError(group.kind)


def _payload_byte(key: str, segment: int = 0):
    digest = hashlib.sha256(f"{key}:{segment}".encode()).digest()
    return digest[0] or 1


class MemoryWritingStore:
    def __init__(self, payloads):
        self.payloads = payloads
        self.loaded_keys = []
        self._lock = threading.Lock()

    def batch_get_into_multi_buffers(self, keys, addrs, sizes):
        results = []
        with self._lock:
            self.loaded_keys.extend(keys)
        for key, key_addrs, key_sizes in zip(keys, addrs, sizes, strict=True):
            if key not in self.payloads:
                results.append(-1)
                continue
            for segment, (address, size) in enumerate(
                zip(key_addrs, key_sizes, strict=True)
            ):
                ctypes.memset(address, _payload_byte(key, segment), size)
            results.append(sum(key_sizes))
        return results


def _database(group_index, group, hash_block_size, buffer):
    database = ChunkedTokenDatabase(
        KeyMetadata(
            model_name=TARGET_MODEL_ID,
            tp_rank=0,
            pcp_rank=0,
            dcp_rank=0,
            pp_rank=0,
            group_id=group_index,
        ),
        block_size=group.block_size,
        hash_block_size=hash_block_size,
    )
    database.set_kv_caches_base_addr([ctypes.addressof(buffer)])
    database.set_block_len([BLOCK_BYTES])
    return database


def receive_plan_trace(profile: ReceiveProfile):
    """Capture the real coordinator/database plan without asserting its shape."""
    coordinator = _coordinator(profile)
    block_hashes = hashes(profile.num_hashes)
    _, hit_length = coordinator.find_longest_cache_hit(
        block_hashes,
        max_length=profile.max_length,
        cached_block_pool=_cached_pool(profile, block_hashes),
    )
    buffers = [(ctypes.c_ubyte * BLOCK_BYTES)() for _group in profile.groups]
    databases = [
        _database(index, group, profile.hash_block_size, buffers[index])
        for index, group in enumerate(profile.groups)
    ]
    masks = coordinator.load_mask(block_hashes, hit_length)
    enumerated_offsets = []
    submitted_offsets = []
    for group_index, database in enumerate(databases):
        group_offsets = []
        submitted_group_offsets = []
        for start, _end, _key in database.process_tokens(hit_length, block_hashes):
            group_offsets.append(start)
            chunk_index = start // database.block_size
            if chunk_index < len(masks[group_index]) and masks[group_index][chunk_index]:
                submitted_group_offsets.append(start)
        enumerated_offsets.append(group_offsets)
        submitted_offsets.append(submitted_group_offsets)
    return {
        "target_model": TARGET_MODEL_ID,
        "reported_external_hit_tokens": hit_length,
        "enumerated_chunk_offsets": enumerated_offsets,
        "load_mask": [list(mask) for mask in masks],
        "submitted_chunk_offsets": submitted_offsets,
    }


def run_receive(profile: ReceiveProfile, *, tp_rank=0, request_count=1):
    coordinator = _coordinator(profile)
    block_hashes = hashes(profile.num_hashes)
    _, hit_length = coordinator.find_longest_cache_hit(
        block_hashes,
        max_length=profile.max_length,
        cached_block_pool=_cached_pool(profile, block_hashes),
    )
    assert hit_length == profile.expected_hit_length

    max_chunks = max(
        profile.max_length // group.block_size for group in profile.groups
    )
    blocks_per_request = max_chunks + 2
    total_blocks = request_count * blocks_per_request + 2
    buffers = [
        (ctypes.c_ubyte * (BLOCK_BYTES * total_blocks))()
        for _group in profile.groups
    ]
    databases = [
        _database(index, group, profile.hash_block_size, buffers[index])
        for index, group in enumerate(profile.groups)
    ]

    expected_key_counter = Counter()
    expected_writes = []
    payloads = {}
    requests = []
    for request_index in range(request_count):
        block_ids_by_group = []
        for group_index, (group, database) in enumerate(
            zip(profile.groups, databases, strict=True)
        ):
            chunks = profile.max_length // group.block_size
            base = request_index * blocks_per_request
            block_ids = [base + chunks - index for index in range(chunks)]
            block_ids_by_group.append(block_ids)
            mask = expected_mask(group, hit_length)
            keys_by_chunk = {
                start // group.block_size: key.to_string()
                for start, _end, key in database.process_tokens(
                    hit_length, block_hashes
                )
            }
            for chunk_index, relevant in enumerate(mask):
                key = keys_by_chunk[chunk_index]
                payloads[key] = True
                block_id = block_ids[chunk_index]
                expected_writes.append(
                    (group_index, block_id, key, relevant)
                )
                if relevant:
                    expected_key_counter[key] += 1
        requests.append(
            ReqMeta(
                req_id=f"{profile.name}-request-{request_index}",
                token_len_chunk=hit_length,
                block_ids=tuple(block_ids_by_group),
                block_hashes=block_hashes,
                load_spec=LoadSpec(
                    vllm_cached_tokens=0,
                    kvpool_cached_tokens=hit_length,
                    can_load=True,
                    token_len=hit_length,
                ),
            )
        )

    store = MemoryWritingStore(payloads)
    ready = threading.Event()
    receiver = KVCacheStoreRecvingThread(
        store=store,
        coord=coordinator,
        token_databases=databases,
        block_size=coordinator.lcm_block_size,
        tp_rank=tp_rank,
        ready_event=ready,
    )
    receiver.start()
    assert ready.wait(timeout=10)
    for request in requests:
        receiver.add_request(request)
    joined = threading.Event()

    def wait_for_queue():
        receiver.request_queue.join()
        joined.set()

    threading.Thread(target=wait_for_queue, daemon=True).start()
    assert joined.wait(timeout=1), "Mooncake receive queue did not drain"
    assert receiver.get_and_clear_finished_requests() == {
        request.req_id for request in requests
    }

    actual_key_counter = Counter(store.loaded_keys)
    assert actual_key_counter == expected_key_counter, {
        "unexpected": actual_key_counter - expected_key_counter,
        "missing": expected_key_counter - actual_key_counter,
    }
    verified = 0
    for group_index, block_id, key, relevant in expected_writes:
        start = block_id * BLOCK_BYTES
        actual = bytes(buffers[group_index][start : start + BLOCK_BYTES])
        expected_byte = _payload_byte(key)
        if relevant:
            assert actual == bytes([expected_byte]) * BLOCK_BYTES
            verified += 1
        else:
            assert actual == bytes(BLOCK_BYTES)
    return ReceiveResult(
        hit_length=hit_length,
        expected_keys=sum(expected_key_counter.values()),
        loaded_keys=len(store.loaded_keys),
        verified_blocks=verified,
        requests=request_count,
        groups=len(profile.groups),
    )


SINGLE_EAGLE_PROFILES = [
    ReceiveProfile(f"single-{b}-{n}", (GroupProfile("full", b),), b, n, b * n, b * (n - 1), True)
    for b, n in ((8, 2), (8, 5), (16, 2), (16, 4), (16, 7), (32, 5))
]

NON_EAGLE_PROFILES = [
    ReceiveProfile(f"plain-{b}-{n}", (GroupProfile("full", b),), b, n, b * n, b * n, False)
    for b, n in ((8, 3), (16, 5), (32, 4))
]

HYBRID_PROFILES = [
    ReceiveProfile(
        f"hybrid-{b}-{w}-{n}",
        (GroupProfile("full", b), GroupProfile("swa", b, w)),
        b,
        n,
        b * n,
        b * (n - 1),
        True,
    )
    for b, w, n in ((8, 16, 6), (8, 24, 7), (16, 32, 5), (16, 48, 7))
]

MIXED_PROFILE = ReceiveProfile(
    "mixed-blocks",
    (GroupProfile("full", 32), GroupProfile("swa", 8, 16)),
    8,
    8,
    64,
    32,
    True,
)

MAMBA_PROFILE = ReceiveProfile(
    "full-mamba",
    (GroupProfile("full", 16), GroupProfile("mamba", 16)),
    16,
    5,
    80,
    80,
    True,
)
