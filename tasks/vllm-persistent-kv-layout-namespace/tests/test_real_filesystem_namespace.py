#!/usr/bin/env python3
"""Exercise persistent namespace isolation through real filesystem I/O."""

from __future__ import annotations

import sys
import tempfile
from unittest.mock import MagicMock

sys.path.insert(0, "/workspace/vllm")

from tests.v1.kv_offload.tiering import test_fs_tier as fs
from vllm.v1.kv_offload.base import OffloadingKVEventsConfig
from vllm.v1.kv_offload.config import (
    OffloadingCacheConfig,
    OffloadingConfig,
    OffloadingModelConfig,
    OffloadingParallelConfig,
)
from vllm.v1.kv_offload.tiering.fs.manager import FileSystemTierManager


def _spec(*, portable: bool, tp_size: int = 1, rank: int = 0):
    spec = MagicMock()
    spec.config = OffloadingConfig(
        groups=(),
        worker_kv_bytes_per_block=0,
        enable_kv_cache_events=False,
        extra_config={},
        engine_id="persistent-layout-e2e",
        model=OffloadingModelConfig(name="facebook/opt-125m", dtype="float32"),
        cache=OffloadingCacheConfig(tokens_per_hash=16, blocks_per_chunk=1),
        parallel=OffloadingParallelConfig(
            rank=rank,
            world_size=tp_size,
            tp_size=tp_size,
            pp_size=1,
            pcp_size=1,
            dcp_size=1,
            data_parallel_index=0,
            is_parallelism_agnostic=portable,
        ),
    )
    spec.blocks_per_chunk = 1
    spec.kv_events_config = OffloadingKVEventsConfig(
        enable_kv_cache_events=False,
        self_describing_kv_events=False,
    )
    return spec


def _tier(root_dir, tensor, spec):
    return FileSystemTierManager(
        offloading_spec=spec,
        primary_kv_view=memoryview(tensor.numpy()),
        tier_type="fs",
        root_dir=root_dir,
        n_read_threads=1,
        n_write_threads=1,
    )


def _successful(results):
    return results and all(result.success for result in results)


def main() -> int:
    tiers = []
    try:
        with tempfile.TemporaryDirectory(prefix="persistent-layout-e2e-") as root:
            producer_tensor = fs._page_aligned_zero_tensor(2, fs._BLOCK_ELEMENTS)
            producer_tensor[0].fill_(17)
            portable_writer = _tier(root, producer_tensor, _spec(portable=True))
            tiers.append(portable_writer)
            portable_writer.submit_store(fs.make_job(1, [fs.key(1)], [0]))
            assert _successful(fs.drain(portable_writer))
            portable_path = portable_writer.file_mapper.base_path
            portable_writer.shutdown()
            tiers.remove(portable_writer)

            consumer_tensor = fs._page_aligned_zero_tensor(2, fs._BLOCK_ELEMENTS)
            layout_specific = _tier(root, consumer_tensor, _spec(portable=False))
            tiers.append(layout_specific)
            assert fs.lookup_and_wait(layout_specific, [fs.key(1)]) == [fs.LookupResult.MISS]
            assert layout_specific.file_mapper.base_path != portable_path

            consumer_tensor[0].fill_(23)
            layout_specific.submit_store(fs.make_job(2, [fs.key(1)], [0]))
            assert _successful(fs.drain(layout_specific))
            consumer_tensor[1].zero_()
            layout_specific.submit_load(
                fs.make_job(3, [fs.key(1)], [1], is_promotion=True)
            )
            assert _successful(fs.drain(layout_specific))
            assert consumer_tensor[1].equal(consumer_tensor[0])

            distributed_tensor = fs._page_aligned_zero_tensor(
                2,
                fs._BLOCK_ELEMENTS,
            )
            portable_reader = _tier(
                root,
                distributed_tensor,
                _spec(portable=True, tp_size=4, rank=3),
            )
            tiers.append(portable_reader)
            assert portable_reader.file_mapper.base_path == portable_path
            assert fs.lookup_and_wait(portable_reader, [fs.key(1)]) == [fs.LookupResult.HIT]
            portable_reader.submit_load(
                fs.make_job(4, [fs.key(1)], [1], is_promotion=True)
            )
            assert _successful(fs.drain(portable_reader))
            assert distributed_tensor[1].equal(producer_tensor[0])

            print(
                {
                    "entrypoint": "FileSystemTierManager",
                    "portable_cross_parallel_hit": True,
                    "incompatible_layout_hit": False,
                    "layout_specific_roundtrip": True,
                    "block_bytes": producer_tensor[0].numel()
                    * producer_tensor.element_size(),
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
    finally:
        for tier in tiers:
            tier.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
