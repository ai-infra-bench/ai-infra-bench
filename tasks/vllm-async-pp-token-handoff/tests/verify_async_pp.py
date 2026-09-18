#!/usr/bin/env python3
"""Behavioral checks at the production async-PP component boundary.

The task contract is independent of the reference patch. Controlled logits
are supplied to real Worker execution; scheduling, model forward, CUDA transport,
request lifecycle and next-forward inputs are real. Neither placeholder values nor token-map contents are scored.
The separate root-owned GPU peer checks real transport against fresh inputs;
worker frames and in-process profiler observations are not a security boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path


from vllm.config import ModelConfig, ParallelConfig, SchedulerConfig, VllmConfig

# Fixtures come from the task-owned, root-staged /tests tree. The candidate
# work tree is deliberately NOT placed on sys.path here: the candidate must
# not be able to supply the fixtures used to judge it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_fixtures import create_requests, create_scheduler  # noqa: E402

NONCE = os.environ.get("ASYNC_PP_NONCE", "")
STAGE = os.environ.get("ASYNC_PP_STAGE", "")

# Legacy driver completion labels; independent GPU observations are required.
SENDER_LIFECYCLE = {
    "production_returned": False,
    "downstream_consumed": False,
    "barrier": False,
    "final_report": False,
}


# Counts real work performed, reported to the supervisor for comparison against
# the expected test invocations. Counts and digests are diagnostic observations;
# they do not by themselves prove execution against malicious candidate code.
CALL_COUNTS = {
    "config_built": 0,
    "schedule_calls": 0,
    "sample_tokens_calls": 0,
    "execute_model_calls": 0,
    "gpu_broadcasts": 0,
}


def assert_privilege_dropped() -> int:
    """Fail closed unless this worker really runs as the expected unprivileged uid."""
    expect = os.environ.get("ASYNC_PP_EXPECT_UID")
    actual = os.getuid()
    assert expect is not None, "ASYNC_PP_EXPECT_UID not supplied by the supervisor"
    assert actual == int(expect), (
        f"worker uid not dropped: running as {actual}, expected {expect}"
    )
    assert actual != 0, "worker must not run as root"
    return actual


def emit_frame(payload: dict) -> None:
    """Emit the single framed payload the trusted supervisor consumes.

    The nonce is minted by the supervisor after the candidate tree is already on
    disk, so a pre-planted or replayed payload cannot carry it. Any stage that
    dies before this call leaves its required stage unsatisfied.
    """
    body = dict(payload)
    body.setdefault("stage", STAGE)
    body.setdefault("rank", int(os.environ.get("RANK", "0")))
    body["stage_completed"] = True
    # Claimed uid is checked against the parent's independent /proc observation.
    body["actual_uid"] = os.getuid()
    body["call_counts"] = dict(CALL_COUNTS)
    print(
        f"##ASYNC_PP_PAYLOAD {NONCE} " + json.dumps(body, sort_keys=True) + " ##END",
        flush=True,
    )


LOCAL_MODEL_CONFIG = str(
    (Path(__file__).resolve().parent / "fixtures/opt-125m").resolve()
)


class TargetInvariantFailure(RuntimeError):
    """An owned target-boundary invariant was violated.

    Classified as FAIL with a reason code. Other execution errors also prevent
    a passing score, but require diagnosis before attributing their cause.
    """

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def check_config() -> int:
    cfg = VllmConfig(
        model_config=ModelConfig(
            model=LOCAL_MODEL_CONFIG,
            skip_tokenizer_init=True,
            max_model_len=2048,
        ),
        scheduler_config=SchedulerConfig(
            max_model_len=2048,
            is_encoder_decoder=False,
            async_scheduling=True,
        ),
        parallel_config=ParallelConfig(
            pipeline_parallel_size=2,
            distributed_executor_backend="mp",
            nnodes=1,
        ),
    )
    if cfg.scheduler_config.async_scheduling is not True:
        raise TargetInvariantFailure(
            "async_scheduling_with_pp_rejected",
            "async scheduling must be allowed together with pipeline parallelism",
        )
    if cfg.parallel_config.pipeline_parallel_size != 2:
        raise TargetInvariantFailure(
            "pipeline_parallel_size_not_preserved",
            "pipeline_parallel_size must round-trip as 2",
        )
    CALL_COUNTS["config_built"] += 1
    emit_frame(
        {
            "async_scheduling_allowed": bool(
                cfg.scheduler_config.async_scheduling
            ),
            "pipeline_parallel_size": int(
                cfg.parallel_config.pipeline_parallel_size
            ),
        }
    )
    print("config_preflight=PASS private_helper_names_scored=false")
    return 0


def check_scheduler_reentry() -> int:
    """Exercise the real next-round scheduler after output placeholders exist."""

    cases = []
    for request_count in (1, 3):
        scheduler = create_scheduler(
            model=LOCAL_MODEL_CONFIG,
            async_scheduling=True,
            pipeline_parallel_size=2,
            skip_tokenizer_init=True,
        )
        requests = create_requests(num_requests=request_count, num_tokens=8)
        for request in requests:
            scheduler.add_request(request)
        first = scheduler.schedule()
        CALL_COUNTS["schedule_calls"] += 1
        expected_ids = {request.request_id for request in requests}
        if set(first.num_scheduled_tokens) != expected_ids:
            raise TargetInvariantFailure(
                "first_round_scheduling_mismatch",
                f"{sorted(first.num_scheduled_tokens)} != {sorted(expected_ids)}",
            )
        # Re-enter the production scheduler before update_from_output. Async PP
        # must schedule the next in-flight step directly, not insert an extra
        # skipped round because placeholders are present.
        second = scheduler.schedule()
        CALL_COUNTS["schedule_calls"] += 1
        if set(second.num_scheduled_tokens) != expected_ids:
            raise TargetInvariantFailure(
                "next_round_not_rescheduled_with_placeholders",
                "async PP must reschedule in-flight requests that still hold "
                f"output placeholders; got {sorted(second.num_scheduled_tokens)} "
                f"!= {sorted(expected_ids)}",
            )
        cases.append(
            {
                "next_round_scheduled_ids": sorted(second.num_scheduled_tokens),
                "request_count": request_count,
            }
        )
    from lifecycle_cases import scheduler_lifecycle
    try:
        lifecycle = scheduler_lifecycle(LOCAL_MODEL_CONFIG)
    except AssertionError as exc:
        raise TargetInvariantFailure("scheduler_output_lifecycle", str(exc)) from exc
    print(json.dumps({"scheduler_reentry": cases, "closed_loop": lifecycle}, sort_keys=True))
    emit_frame({
        "scheduler_reentry_cases": cases,
        "scheduler_reentry_request_counts": [c["request_count"] for c in cases],
    })
    print("ASYNC_PP_SCHEDULER_REENTRY=PASS")
    return 0


def run_suite(kind):
    if kind == 'cpu':
        original_emit = globals()['emit_frame']
        reports = []
        globals()['emit_frame'] = reports.append
        try:
            check_config()
            check_scheduler_reentry()
        finally:
            globals()['emit_frame'] = original_emit
        emit_frame({'async_scheduling_allowed': reports[0]['async_scheduling_allowed'],
                    'pipeline_parallel_size': reports[0]['pipeline_parallel_size'],
                    'scheduler_reentry_request_counts': reports[1]['scheduler_reentry_request_counts']})
    else:
        from mp_behavior import run
        scenarios = run()
        emit_frame({'scenarios_passed': scenarios, 'world_size': 2,
                    'sender_lifecycle': dict.fromkeys(SENDER_LIFECYCLE, True)})
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite', choices=('cpu', 'gpu'), required=True)
    args = parser.parse_args()
    assert_privilege_dropped()
    try:
        return run_suite(args.suite)
    except (TargetInvariantFailure, AssertionError) as exc:
        print(json.dumps({'verdict': 'FAIL', 'detail': str(exc),
                          'traceback': traceback.format_exc()}), flush=True)
        return 1
    except Exception as exc:
        # The exception may originate in the candidate, verifier, or environment.
        # This label records an execution failure without assigning blame.
        print(json.dumps({'verdict': 'EXECUTION_ERROR', 'detail': str(exc),
                          'traceback': traceback.format_exc()}), flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
