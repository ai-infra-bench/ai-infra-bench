from math import ceil

import pytest
from vllm.v1.core.kv_cache_utils import BlockHashListWithBlockSize

from .test_mooncake_store_coordinator import (
    ExternalCachedBlockPool,
    KVCacheGroupSpec,
    _full,
    _hashes,
    _make_coord,
    _swa,
)


def _all_cached(group_ids, hashes):
    return ExternalCachedBlockPool(
        {(group_id, bytes(value)) for group_id in group_ids for value in hashes}
    )


@pytest.mark.parametrize(
    "block_size,num_blocks",
    [(8, 2), (8, 5), (16, 2), (16, 4), (16, 7), (32, 5)],
    ids=["b8-n2", "b8-n5", "b16-n2", "b16-n4", "b16-n7", "b32-n5"],
)
def test_eagle_receive_mask_covers_reported_hit(block_size, num_blocks):
    groups = [KVCacheGroupSpec(["full"], _full(block_size))]
    coordinator = _make_coord(
        groups,
        hash_block_size=block_size,
        use_eagle=True,
    )
    hashes = _hashes(num_blocks)
    cached = _all_cached((0,), hashes)

    _, hit_length = coordinator.find_longest_cache_hit(
        hashes,
        max_length=block_size * num_blocks,
        cached_block_pool=cached,
    )
    masks = coordinator.load_mask(hashes, token_len=hit_length)

    assert hit_length == block_size * (num_blocks - 1)
    assert masks == ([True] * (num_blocks - 1),)


@pytest.mark.parametrize(
    "block_size,num_blocks",
    [(8, 3), (16, 5), (32, 4)],
    ids=["b8", "b16", "b32"],
)
def test_non_eagle_lookup_and_receive_mask_are_unchanged(block_size, num_blocks):
    groups = [KVCacheGroupSpec(["full"], _full(block_size))]
    coordinator = _make_coord(
        groups,
        hash_block_size=block_size,
        use_eagle=False,
    )
    hashes = _hashes(num_blocks)
    cached = _all_cached((0,), hashes)

    _, hit_length = coordinator.find_longest_cache_hit(
        hashes,
        max_length=block_size * num_blocks,
        cached_block_pool=cached,
    )

    assert hit_length == block_size * num_blocks
    assert coordinator.load_mask(hashes, token_len=hit_length) == (
        [True] * num_blocks,
    )


@pytest.mark.parametrize(
    "block_size,window,num_blocks",
    [(8, 16, 6), (8, 24, 7), (16, 32, 5), (16, 48, 7)],
    ids=["b8-w16", "b8-w24", "b16-w32", "b16-w48"],
)
def test_hybrid_receive_mask_preserves_full_and_sliding_window_semantics(
    block_size,
    window,
    num_blocks,
):
    groups = [
        KVCacheGroupSpec(["full"], _full(block_size)),
        KVCacheGroupSpec(["swa"], _swa(block_size, window)),
    ]
    coordinator = _make_coord(
        groups,
        hash_block_size=block_size,
        use_eagle=True,
    )
    hashes = _hashes(num_blocks)
    cached = _all_cached((0, 1), hashes)

    _, hit_length = coordinator.find_longest_cache_hit(
        hashes,
        max_length=block_size * num_blocks,
        cached_block_pool=cached,
    )
    masks = coordinator.load_mask(hashes, token_len=hit_length)

    chunks = num_blocks - 1
    tail_chunks = min(chunks, ceil((window - 1) / block_size))
    assert hit_length == chunks * block_size
    assert masks[0] == [True] * chunks
    assert masks[1] == [False] * (chunks - tail_chunks) + [True] * tail_chunks


def test_mixed_block_sizes_cover_same_reported_token_range():
    groups = [
        KVCacheGroupSpec(["full"], _full(32)),
        KVCacheGroupSpec(["swa"], _swa(8, 16)),
    ]
    coordinator = _make_coord(groups, hash_block_size=8, use_eagle=True)
    hashes = _hashes(8)
    full_hashes = list(BlockHashListWithBlockSize(hashes, 8, 32))
    cached = ExternalCachedBlockPool(
        {(0, bytes(value)) for value in full_hashes}
        | {(1, bytes(value)) for value in hashes}
    )

    _, hit_length = coordinator.find_longest_cache_hit(
        hashes,
        max_length=64,
        cached_block_pool=cached,
    )
    masks = coordinator.load_mask(hashes, token_len=hit_length)

    assert hit_length == 32
    assert masks[0] == [True]
    assert masks[1] == [False, False, True, True]
