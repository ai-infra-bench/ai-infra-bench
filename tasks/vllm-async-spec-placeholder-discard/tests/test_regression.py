from __future__ import annotations

import pytest

from verifier_support import (
    activate_requests,
    assert_stale_frame_did_not_change_fresh_state,
    capture_spec_frame,
    deliver,
    make_requests,
    make_scheduler,
    resume_after_reset,
    snapshot,
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
    scheduler = make_scheduler(tmp_path / "model")
    request = make_requests(1)[0]
    activate_requests(scheduler, [request])
    computed_before = request.num_computed_tokens
    output_before = len(request.output_token_ids)
    scheduler_output = capture_spec_frame(
        scheduler,
        [request],
        num_drafts=num_drafts,
        num_accepted=num_accepted,
    )
    deliver(scheduler, scheduler_output)
    assert request.num_output_placeholders == 0
    assert request.num_computed_tokens == computed_before + num_accepted + 1
    assert len(request.output_token_ids) == output_before + num_accepted + 1


def test_reset_after_drained_frame_preserves_speculative_progress(tmp_path):
    scheduler = make_scheduler(tmp_path / "model")
    request = make_requests(1)[0]
    activate_requests(scheduler, [request])
    completed = capture_spec_frame(
        scheduler, [request], num_drafts=3, num_accepted=1
    )
    deliver(scheduler, completed)
    before_length = len(request.output_token_ids)

    resumed = resume_after_reset(scheduler, [request])
    deliver(scheduler, resumed)
    current = capture_spec_frame(
        scheduler, [request], num_drafts=5, num_accepted=3
    )
    deliver(scheduler, current)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == before_length + 5


def test_non_speculative_async_frame_is_unchanged(tmp_path):
    scheduler = make_scheduler(tmp_path / "model")
    request = make_requests(1)[0]
    activate_requests(scheduler, [request])
    before_length = len(request.output_token_ids)
    scheduler_output = capture_spec_frame(
        scheduler, [request], num_drafts=0, num_accepted=0
    )
    deliver(scheduler, scheduler_output)
    assert request.num_output_placeholders == 0
    assert len(request.output_token_ids) == before_length + 1


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


def test_stale_batch_isolated_from_current_batch(tmp_path):
    scheduler = make_scheduler(tmp_path / "model", max_num_seqs=32)
    requests = make_requests(3)
    activate_requests(scheduler, requests)
    stale_output = capture_spec_frame(
        scheduler, requests, num_drafts=5, num_accepted=2
    )
    current_output = resume_after_reset(scheduler, requests)
    before = {request.request_id: snapshot(request) for request in requests}
    deliver(scheduler, stale_output)
    for request in requests:
        assert_stale_frame_did_not_change_fresh_state(
            request, before[request.request_id]
        )

    lengths = {
        request.request_id: len(request.output_token_ids) for request in requests
    }
    deliver(scheduler, current_output)
    for request in requests:
        assert request.num_output_placeholders == 0
        assert len(request.output_token_ids) == lengths[request.request_id] + 1
