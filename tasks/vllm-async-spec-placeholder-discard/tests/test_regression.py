from __future__ import annotations

import pytest

from verifier_support import (
    assert_stale_frame_did_not_change_fresh_state,
    deliver,
    manual_running_scheduler,
    snapshot,
    synthetic_frame,
)


@pytest.mark.parametrize(
    ("num_drafts", "num_accepted", "fresh_placeholders"),
    [
        (1, 0, 1),
        (2, 0, 2),
        (3, 1, 1),
        (5, 0, 1),
        (5, 3, 2),
        (7, 2, 4),
    ],
    ids=[
        "one-draft",
        "two-drafts",
        "partial-three",
        "all-rejected-five",
        "partial-five",
        "partial-seven",
    ],
)
def test_stale_spec_frame_preserves_resumed_request_behavior(
    tmp_path,
    num_drafts,
    num_accepted,
    fresh_placeholders,
):
    scheduler, (request,) = manual_running_scheduler(tmp_path)
    request.num_output_placeholders = fresh_placeholders
    request.async_tokens_to_discard = num_drafts + 1
    before = snapshot(request)
    scheduler_output, runner_output = synthetic_frame(
        [(request, num_drafts, num_accepted)]
    )
    scheduler.update_from_output(scheduler_output, runner_output)
    assert_stale_frame_did_not_change_fresh_state(request, before)


@pytest.mark.parametrize(
    ("num_drafts", "num_accepted"),
    [(1, 0), (3, 1), (5, 0), (7, 7)],
    ids=["one-rejected", "partial", "all-rejected", "all-accepted"],
)
def test_ordinary_spec_acceptance_and_rejection_are_unchanged(
    tmp_path, num_drafts, num_accepted
):
    scheduler, (request,) = manual_running_scheduler(tmp_path)
    request.num_output_placeholders = num_drafts + 1
    computed_before = request.num_computed_tokens
    scheduler_output, runner_output = synthetic_frame(
        [(request, num_drafts, num_accepted)]
    )
    scheduler.update_from_output(scheduler_output, runner_output)
    assert request.num_output_placeholders == 0
    assert request.num_computed_tokens == computed_before - (
        num_drafts - num_accepted
    )
    assert len(request.output_token_ids) == num_accepted + 1


def test_empty_stale_result_does_not_change_resumed_state(tmp_path):
    scheduler, (request,) = manual_running_scheduler(tmp_path)
    request.num_output_placeholders = 3
    request.async_tokens_to_discard = 2
    before = snapshot(request)
    scheduler_output, runner_output = synthetic_frame([(request, 5, 0)])
    runner_output.sampled_token_ids = [[]]
    scheduler.update_from_output(scheduler_output, runner_output)
    assert_stale_frame_did_not_change_fresh_state(request, before)


def test_non_speculative_async_frame_is_unchanged(tmp_path):
    scheduler, (request,) = manual_running_scheduler(tmp_path)
    request.num_output_placeholders = 1
    scheduler_output, runner_output = synthetic_frame([(request, 0, 0)])
    scheduler.update_from_output(scheduler_output, runner_output)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == 1


@pytest.mark.parametrize("num_drafts", [1, 3, 7])
def test_stale_frames_drain_then_normal_output_makes_progress(
    tmp_path, num_drafts
):
    scheduler, (request,) = manual_running_scheduler(tmp_path)
    request.num_output_placeholders = 1
    request.async_tokens_to_discard = num_drafts + 1
    stale_output, stale_runner = synthetic_frame([(request, num_drafts, 0)])
    before = snapshot(request)
    for _ in range(num_drafts + 1):
        scheduler.update_from_output(stale_output, stale_runner)
        assert_stale_frame_did_not_change_fresh_state(request, before)

    ordinary_output, ordinary_runner = synthetic_frame([(request, 0, 0)])
    scheduler.update_from_output(ordinary_output, ordinary_runner)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == 1
