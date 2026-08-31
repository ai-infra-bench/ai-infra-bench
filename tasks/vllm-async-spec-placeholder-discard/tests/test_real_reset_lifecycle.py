#!/usr/bin/env python3
"""Exercise reset and stale-output handling through a real AsyncScheduler."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/workspace/vllm")

from tests.v1.core import test_harbor_async_spec_placeholder_discard as suite
from vllm.v1.outputs import ModelRunnerOutput


def _run_cycle(num_drafts: int) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix=f"async-reset-{num_drafts}-") as temp_dir:
        scheduler = suite.create_scheduler(
            model=suite._tiny_model(Path(temp_dir)),
            async_scheduling=True,
            skip_tokenizer_init=True,
            max_model_len=1024,
            max_num_batched_tokens=1024,
        )
    scheduler.num_spec_tokens = num_drafts
    request = suite.create_requests(num_requests=1, max_tokens=128)[0]
    request.append_output_token_ids(42)
    scheduler.add_request(request)
    request.num_computed_tokens = request.num_tokens - 1

    stale_scheduler_output = scheduler.schedule()
    assert request.num_output_placeholders == 1
    stale_scheduler_output.scheduled_spec_decode_tokens[request.request_id] = list(
        range(100, 100 + num_drafts)
    )
    stale_scheduler_output.num_scheduled_tokens[request.request_id] = num_drafts + 1
    stale_scheduler_output.total_num_scheduled_tokens = num_drafts + 1
    request.num_output_placeholders += num_drafts

    assert scheduler.reset_prefix_cache(reset_running_requests=True) is True
    assert request.num_output_placeholders == 0
    assert request.async_tokens_to_discard > 0

    request.num_computed_tokens = request.num_tokens - 1
    scheduler.schedule()
    assert request.num_output_placeholders == 1
    computed_before = request.num_computed_tokens

    stale_model_output = ModelRunnerOutput(
        req_ids=[request.request_id],
        req_id_to_index={request.request_id: 0},
        sampled_token_ids=[[999]],
        logprobs=None,
        prompt_logprobs_dict={},
        pooler_output=[],
    )
    discard_before = request.async_tokens_to_discard
    scheduler.update_from_output(stale_scheduler_output, stale_model_output)

    assert request.num_output_placeholders == 1
    assert request.num_computed_tokens == computed_before
    assert request.async_tokens_to_discard == discard_before - 1
    return {
        "drafts": num_drafts,
        "placeholders": request.num_output_placeholders,
        "discard_remaining": request.async_tokens_to_discard,
    }


def main() -> int:
    try:
        cycles = [_run_cycle(num_drafts) for num_drafts in (2, 5, 7)]
        print(
            {
                "entrypoint": "AsyncScheduler.reset_prefix_cache",
                "cycles": cycles,
                "negative_placeholder_events": 0,
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
