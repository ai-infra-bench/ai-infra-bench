#!/usr/bin/env python3
"""Run 24 requests through eleven overlapping reset and resume cycles."""

from __future__ import annotations

import tempfile
from pathlib import Path

from verifier_support import (
    activate_requests,
    assert_stale_frame_did_not_change_fresh_state,
    capture_spec_frame,
    deliver,
    make_requests,
    make_scheduler,
    model_output,
    resume_after_reset,
    snapshot,
)


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="async-spec-reset-e2e-") as temp_dir:
            scheduler = make_scheduler(Path(temp_dir) / "model", max_num_seqs=32)
            requests = make_requests(24, max_tokens=128, token_seed=300)
            activate_requests(scheduler, requests)
            stale_draft_widths = [5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

            current_output = capture_spec_frame(
                scheduler,
                requests,
                num_drafts=stale_draft_widths[0],
                num_accepted=3,
            )
            stale_outputs = []
            for _cycle in range(len(stale_draft_widths)):
                stale_outputs.append(current_output)
                current_output = resume_after_reset(scheduler, requests)

            fresh_output = current_output
            fresh_snapshots = {
                request.request_id: snapshot(request) for request in requests
            }

            for stale_index, stale_output in enumerate(stale_outputs):
                scheduler.update_from_output(
                    stale_output,
                    model_output(
                        stale_output,
                        token_seed=1000 + stale_index * 200,
                    ),
                )
                for request in requests:
                    assert_stale_frame_did_not_change_fresh_state(
                        request,
                        fresh_snapshots[request.request_id],
                    )

            before_lengths = {
                request.request_id: len(request.output_token_ids)
                for request in requests
            }
            deliver(scheduler, fresh_output, accepted=0, token_seed=5000)
            for request in requests:
                assert request.num_output_placeholders >= 0
                assert len(request.output_token_ids) == (
                    before_lengths[request.request_id] + 1
                )

        print(
            "ASYNC_SPEC_LIFECYCLE_RESULT "
            + repr(
                {
                    "completed": True,
                    "entrypoint": (
                        "AsyncScheduler schedule/reset/update lifecycle"
                    ),
                    "concurrent_requests": 24,
                    "reset_cycles": len(stale_draft_widths),
                    "stale_frame_draft_widths": stale_draft_widths,
                    "stale_request_frames_delivered": (
                        len(stale_outputs) * len(requests)
                    ),
                    "stale_placeholder_tokens_discarded": sum(
                        num_drafts + 1 for num_drafts in stale_draft_widths
                    )
                    * len(requests),
                    "normal_progress_events": len(requests),
                    "negative_placeholder_events": 0,
                }
            ),
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            {
                "error": type(exc).__name__,
                "message": str(exc).splitlines()[0] if str(exc) else "no message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
