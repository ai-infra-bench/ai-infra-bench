from __future__ import annotations

from verifier_support import (
    admission_blocks,
    async_free_timeline,
    competing_load_reuse,
    connector_handoff_distinct_block_count,
    pipeline_free_timeline,
    speculative_rollback_window,
    sync_free_timeline,
)


def test_async_swa_holds_blocks_until_output_is_processed(tmp_path) -> None:
    timeline = async_free_timeline(tmp_path, "swa")
    assert timeline["before_process"] == timeline["after_prefill"]
    assert timeline["after_process"] - timeline["after_prefill"] == 5


def test_async_chunked_local_holds_blocks_until_output_is_processed(tmp_path) -> None:
    timeline = async_free_timeline(tmp_path, "chunked")
    assert timeline["before_process"] == timeline["after_prefill"]
    assert timeline["after_process"] - timeline["after_prefill"] == 6


def test_sync_swa_keeps_immediate_freeing(tmp_path) -> None:
    timeline = sync_free_timeline(tmp_path, "swa")
    assert timeline["after_decode"] - timeline["before_decode"] == 5


def test_sync_chunked_local_keeps_immediate_freeing(tmp_path) -> None:
    timeline = sync_free_timeline(tmp_path, "chunked")
    assert timeline["after_decode"] - timeline["before_decode"] == 6


def test_async_blocks_are_not_double_freed(tmp_path) -> None:
    for kind in ("swa", "chunked"):
        timeline = async_free_timeline(tmp_path / kind, kind)
        assert timeline["after_next"] == timeline["after_process"]


def test_full_attention_does_not_midflight_free(tmp_path) -> None:
    timeline = async_free_timeline(tmp_path, "full")
    assert timeline["before_process"] == timeline["after_prefill"]
    assert timeline["after_process"] == timeline["after_prefill"]


def test_connector_handoff_keeps_inflight_window_blocks(tmp_path) -> None:
    assert connector_handoff_distinct_block_count(tmp_path) == 7


def test_competing_load_cannot_reuse_inflight_reader_blocks(tmp_path) -> None:
    for kind in ("swa", "chunked"):
        result = competing_load_reuse(tmp_path / kind, kind)
        assert result["premature_overlap"] == []


def test_speculative_rollback_keeps_required_window_blocks(tmp_path) -> None:
    for kind, rollback in (("swa", 47), ("chunked", 35)):
        result = speculative_rollback_window(
            tmp_path / kind,
            kind,
            rollback_tokens=rollback,
        )
        assert result["required_blocks_retained"], result


def test_async_admission_reserves_for_overlapping_batches(tmp_path) -> None:
    for kind in ("swa", "chunked"):
        synchronous = admission_blocks(
            tmp_path / f"{kind}-sync",
            kind,
            async_scheduling=False,
        )
        asynchronous = admission_blocks(
            tmp_path / f"{kind}-async",
            kind,
            async_scheduling=True,
        )
        assert asynchronous > synchronous
        full_attention = admission_blocks(
            tmp_path / f"{kind}-full",
            "full",
            async_scheduling=True,
        )
        # Recycling-aware attention must never reserve materially more than
        # the non-recycling full-attention ceiling for the same model length.
        assert asynchronous <= full_attention + 1


def test_pipeline_overlap_holds_window_blocks_and_reserves_capacity(tmp_path) -> None:
    for kind, released in (("swa", 5), ("chunked", 6)):
        timeline = pipeline_free_timeline(tmp_path / kind, kind)
        assert timeline["before_process"] == timeline["after_prefill"]
        assert timeline["after_process"] - timeline["after_prefill"] == released
        pipeline = admission_blocks(
            tmp_path / f"{kind}-pipeline",
            kind,
            async_scheduling=False,
            pipeline_parallel_size=2,
        )
        synchronous = admission_blocks(
            tmp_path / f"{kind}-sync",
            kind,
            async_scheduling=False,
        )
        assert pipeline > synchronous
