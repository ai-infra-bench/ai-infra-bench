#!/usr/bin/env python3
"""Curator-only lifecycle challenge outside the verifier case inventory."""

from pathlib import Path
import tempfile

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


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="async-spec-independent-") as temp:
        scheduler = make_scheduler(Path(temp) / "model", max_num_seqs=16)
        requests = make_requests(5, token_seed=600)
        activate_requests(scheduler, requests)

        wide_stale = capture_spec_frame(
            scheduler,
            requests,
            num_drafts=6,
            num_accepted=4,
        )
        narrow_stale = resume_after_reset(scheduler, requests)
        current = resume_after_reset(scheduler, requests)
        resumed = {request.request_id: snapshot(request) for request in requests}

        deliver(scheduler, wide_stale, token_seed=4000)
        deliver(scheduler, narrow_stale, token_seed=5000)
        for request in requests:
            assert_stale_frame_did_not_change_fresh_state(
                request, resumed[request.request_id]
            )

        lengths = {
            request.request_id: len(request.output_token_ids) for request in requests
        }
        deliver(scheduler, current, token_seed=6000)
        for request in requests:
            assert request.num_output_placeholders == 0
            assert len(request.output_token_ids) == lengths[request.request_id] + 1

        next_frame = capture_spec_frame(
            scheduler,
            requests,
            num_drafts=4,
            num_accepted=2,
        )
        deliver(scheduler, next_frame, token_seed=7000)
        for request in requests:
            assert request.num_output_placeholders == 0
            assert len(request.output_token_ids) == lengths[request.request_id] + 4

    print(
        {
            "passed": True,
            "requests": 5,
            "reset_cycles": 2,
            "stale_draft_widths": [6, 0],
            "fresh_speculative_width": 4,
            "fresh_accepted_drafts": 2,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
