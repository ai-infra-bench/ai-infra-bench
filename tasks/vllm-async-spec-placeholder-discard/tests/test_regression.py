from __future__ import annotations

import pytest

from verifier_support import (
    activate_requests,
    assert_stale_frame_did_not_change_fresh_state,
    capture_spec_frame,
    deliver,
    make_requests,
    make_scheduler,
    manual_running_scheduler,
    resume_after_reset,
    snapshot,
    synthetic_frame,
)


@pytest.mark.parametrize(
    ("num_drafts", "num_accepted"),
    [
        (1, 0),
        (2, 0),
        (3, 1),
        (5, 0),
        (5, 3),
        (7, 2),
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
def test_one_stale_spec_frame_then_fresh_output_makes_progress(
    tmp_path, num_drafts, num_accepted
):
    scheduler = make_scheduler(tmp_path / "model")
    requests = make_requests(1)
    request = requests[0]
    activate_requests(scheduler, requests)
    stale_output = capture_spec_frame(
        scheduler,
        requests,
        num_drafts=num_drafts,
        num_accepted=num_accepted,
    )
    fresh_output = resume_after_reset(scheduler, requests)
    before = snapshot(request)
    deliver(scheduler, stale_output)
    assert_stale_frame_did_not_change_fresh_state(request, before)

    before_length = len(request.output_token_ids)
    deliver(scheduler, fresh_output, accepted=0)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == before_length + 1


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
def test_overlapping_resets_discard_each_stale_frame_then_make_progress(
    tmp_path, num_drafts
):
    scheduler = make_scheduler(tmp_path / "model")
    requests = make_requests(1)
    request = requests[0]
    activate_requests(scheduler, requests)
    first_stale = capture_spec_frame(
        scheduler, requests, num_drafts=num_drafts, num_accepted=num_drafts
    )
    second_stale = resume_after_reset(scheduler, requests)
    fresh_output = resume_after_reset(scheduler, requests)
    before = snapshot(request)

    deliver(scheduler, first_stale)
    assert_stale_frame_did_not_change_fresh_state(request, before)
    deliver(scheduler, second_stale, accepted=0)
    assert_stale_frame_did_not_change_fresh_state(request, before)

    before_length = len(request.output_token_ids)
    deliver(scheduler, fresh_output, accepted=0)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == before_length + 1


def test_stale_and_current_requests_are_isolated_in_one_batch(tmp_path):
    scheduler, requests = manual_running_scheduler(tmp_path, count=3)
    stale_left, current, stale_right = requests
    stale_left.num_output_placeholders = 2
    stale_left.async_tokens_to_discard = 2
    current.num_output_placeholders = 4
    stale_right.num_output_placeholders = 6
    stale_right.async_tokens_to_discard = 6
    stale_before = {
        request.request_id: snapshot(request)
        for request in (stale_left, stale_right)
    }
    computed_before = current.num_computed_tokens
    scheduler_output, runner_output = synthetic_frame(
        [
            (stale_left, 1, 1),
            (current, 3, 2),
            (stale_right, 5, 0),
        ]
    )

    scheduler.update_from_output(scheduler_output, runner_output)

    for request in (stale_left, stale_right):
        assert_stale_frame_did_not_change_fresh_state(
            request, stale_before[request.request_id]
        )
    assert current.num_output_placeholders == 0
    assert current.num_computed_tokens == computed_before - 1
    assert len(current.output_token_ids) == 3
