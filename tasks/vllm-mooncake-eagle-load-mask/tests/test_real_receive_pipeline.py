#!/usr/bin/env python3
"""Exercise Mooncake's real background receive path with an in-memory store."""

from __future__ import annotations

import sys
import threading

sys.path.insert(0, "/workspace/vllm")

from tests.v1.kv_connector.unit import test_harbor_mooncake_eagle_mask as suite
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.store.data import (
    ChunkedTokenDatabase,
    KeyMetadata,
    LoadSpec,
    ReqMeta,
)
from vllm.distributed.kv_transfer.kv_connector.v1.mooncake.store.worker import (
    KVCacheStoreRecvingThread,
)


class RecordingStore:
    def __init__(self):
        self.batches = []

    def batch_get_into_multi_buffers(self, keys, addrs, sizes):
        self.batches.append((list(keys), list(addrs), list(sizes)))
        return [sum(item) for item in sizes]


def _database(group_id: int, block_size: int) -> ChunkedTokenDatabase:
    database = ChunkedTokenDatabase(
        KeyMetadata(
            model_name="minimax",
            tp_rank=0,
            pcp_rank=0,
            dcp_rank=0,
            pp_rank=0,
            group_id=group_id,
        ),
        block_size=block_size,
        hash_block_size=block_size,
    )
    database.set_kv_caches_base_addr([0x10000000 + group_id * 0x100000])
    database.set_block_len([64])
    return database


def _run_receive_case(block_size, num_blocks, hybrid):
    groups = [suite.KVCacheGroupSpec(["full"], suite._full(block_size))]
    if hybrid:
        groups.append(
            suite.KVCacheGroupSpec(["swa"], suite._swa(block_size, 2 * block_size))
        )
    coordinator = suite._make_coord(
        groups,
        hash_block_size=block_size,
        use_eagle=True,
    )
    hashes = suite._hashes(num_blocks)
    cached = suite._all_cached(range(len(groups)), hashes)
    _, hit_length = coordinator.find_longest_cache_hit(
        hashes,
        max_length=block_size * num_blocks,
        cached_block_pool=cached,
    )

    databases = [_database(index, block_size) for index in range(len(groups))]
    store = RecordingStore()
    ready = threading.Event()
    receiver = KVCacheStoreRecvingThread(
        store=store,
        coord=coordinator,
        token_databases=databases,
        block_size=coordinator.lcm_block_size,
        tp_rank=0,
        ready_event=ready,
    )
    receiver.start()
    assert ready.wait(timeout=10)

    request_id = f"recv-{block_size}-{num_blocks}-{hybrid}"
    block_ids = tuple(list(range(num_blocks)) for _ in groups)
    request = ReqMeta(
        req_id=request_id,
        token_len_chunk=hit_length,
        block_ids=block_ids,
        block_hashes=hashes,
        load_spec=LoadSpec(
            vllm_cached_tokens=0,
            kvpool_cached_tokens=hit_length,
            can_load=True,
            token_len=hit_length,
        ),
    )
    receiver.add_request(request)
    receiver.request_queue.join()

    assert receiver.get_and_clear_finished_requests() == {request_id}
    assert len(store.batches) == 1
    loaded_keys = store.batches[0][0]
    full_chunks = num_blocks - 1
    expected_keys = full_chunks + (min(2, full_chunks) if hybrid else 0)
    assert len(loaded_keys) == expected_keys
    return {
        "block_size": block_size,
        "reported_hit_tokens": hit_length,
        "groups": len(groups),
        "loaded_keys": len(loaded_keys),
    }


def main() -> int:
    try:
        cases = [
            _run_receive_case(8, 6, False),
            _run_receive_case(16, 4, False),
            _run_receive_case(16, 4, True),
        ]
        print(
            {
                "entrypoint": "KVCacheStoreRecvingThread",
                "cases": cases,
                "transport": "in-memory recording store",
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        lines = str(exc).splitlines()
        print(
            {
                "error": type(exc).__name__,
                "message": lines[0] if lines else "no exception message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
