from __future__ import annotations

import pytest

from verifier_support import (
    HYBRID_PROFILES,
    MAMBA_PROFILE,
    MIXED_PROFILE,
    NON_EAGLE_PROFILES,
    SINGLE_EAGLE_PROFILES,
    run_receive,
)


@pytest.mark.parametrize("profile", SINGLE_EAGLE_PROFILES, ids=lambda p: p.name)
def test_eagle_receive_populates_every_reported_full_attention_chunk(profile):
    result = run_receive(profile)
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


@pytest.mark.parametrize("profile", NON_EAGLE_PROFILES, ids=lambda p: p.name)
def test_non_eagle_receive_behavior_is_unchanged(profile):
    result = run_receive(profile)
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


@pytest.mark.parametrize("profile", HYBRID_PROFILES, ids=lambda p: p.name)
def test_hybrid_full_and_sliding_window_chunks_are_written_correctly(profile):
    result = run_receive(profile)
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


def test_mixed_block_sizes_write_the_reported_token_range():
    result = run_receive(MIXED_PROFILE)
    assert result.hit_length == 32
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


def test_full_attention_and_mamba_group_contents_are_preserved():
    result = run_receive(MAMBA_PROFILE)
    assert result.hit_length == 80
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


@pytest.mark.parametrize("tp_rank", [1, 2])
def test_tp_rotation_changes_order_not_loaded_content(tp_rank):
    result = run_receive(HYBRID_PROFILES[2], tp_rank=tp_rank)
    assert result.loaded_keys == result.expected_keys == result.verified_blocks


def test_multiple_requests_share_one_receive_queue_without_dropping_chunks():
    result = run_receive(HYBRID_PROFILES[1], tp_rank=1, request_count=4)
    assert result.requests == 4
    assert result.loaded_keys == result.expected_keys == result.verified_blocks
