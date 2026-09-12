#!/usr/bin/env python3
"""Two-rank production-lifecycle contract for async PP sampled tokens.

Fairness model (see validation/semantic-boundary.md). The target contract is:
the last PP rank hands the freshly sampled token ids to earlier ranks as an
on-GPU NCCL collective, earlier ranks rebuild ``prev_sampled_token_ids`` on the
GPU and the kept/discarded bookkeeping, and NO CPU/object collective or
GPU->CPU scalar sync is used on that path.

Every reward-zeroing decision is therefore classified:

  * A violation of an owned target invariant raises the typed
    ``TargetInvariantFailure(code, detail)``. Both ranks agree via an on-GPU
    all-reduce, rank 0 emits a JSON record plus exactly one classified marker
    (``ASYNC_PP_NCCL_SCENARIO=FAIL``) flushed BEFORE the barrier, and both ranks
    exit 1. This is the ONLY way a Base/control run legitimately scores 0.

  * ANY other exception (missing fixture attribute, AttributeError, KeyError,
    NCCL/CUDA init error, unclassified RuntimeError, ...) is treated as an
    infrastructure failure: the rank prints ``ASYNC_PP_INFRA_ERROR`` with a
    traceback and exits 2 WITHOUT a PASS marker. The verifier fails closed --
    such a crash is never counted as a valid "the implementation failed the
    contract" outcome.

The model-free fixtures execute production bookkeeping, async output consumption,
cached-state updates and next-input preparation after the real GPU collective.

The independent curator challenge (validation/challenge/challenge_token_handoff.py)
re-derives these same invariants on a distinct fresh scenario; this verifier does
not weaken any of them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import torch.distributed as dist

import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.config import ParallelConfig, SchedulerConfig, VllmConfig
from vllm.v1.worker.gpu_model_runner import GPUModelRunner

# Fixtures come from the task-owned, root-staged /tests tree. The candidate
# work tree is deliberately NOT placed on sys.path here: the candidate must
# not be able to supply the fixtures used to judge it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_fixtures import create_requests, create_scheduler  # noqa: E402
from worker_fixtures import make_runner, next_inputs
from handoff_observer import HandoffObserver

NONCE = os.environ.get("ASYNC_PP_NONCE", "")
STAGE = os.environ.get("ASYNC_PP_STAGE", "")

# Records the post-broadcast protocol steps a sender actually completed.
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


def payload_digest(stage: str, tokens) -> str:
    """Digest over the tokens this rank actually handled.

    Compared with the supervisor's independent expectation. This is a content
    consistency check, not an unforgeable proof of execution.
    """
    canonical = json.dumps({"stage": stage, "tokens": list(tokens)},
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


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
    # Proof of the privilege drop: the supervisor requires the unprivileged uid.
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

    Distinct from arbitrary runtime errors: only this type is accepted as a
    legitimate reward-zeroing outcome (Base/control fail the contract). It is
    lowered to a single classified ``...=FAIL`` marker with a reason code.
    """

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")








def check_config() -> int:
    cfg = VllmConfig(
        scheduler_config=SchedulerConfig(
            max_model_len=8192,
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
        placeholders = {
            request.request_id: request.num_output_placeholders
            for request in requests
        }
        if not all(count > 0 for count in placeholders.values()):
            raise TargetInvariantFailure(
                "missing_output_placeholders",
                f"expected positive output placeholders, got {placeholders}",
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
                "output_placeholders": placeholders,
                "request_count": request_count,
            }
        )
    print(json.dumps({"scheduler_reentry": cases}, sort_keys=True))
    emit_frame({
        "scheduler_reentry_cases": cases,
        "scheduler_reentry_request_counts": [c["request_count"] for c in cases],
    })
    print("ASYNC_PP_SCHEDULER_REENTRY=PASS")
    return 0


def pp_group(rank: int, world_size: int):
    from worker_fixtures import initialize_runner_groups
    return initialize_runner_groups(rank, world_size)


def receiver_runner(req_ids, discard_mask, prior_outputs):
    return make_runner(req_ids, discard_mask, prior_outputs)



def invoke_production_sample(runner, *, is_sender: bool):
    original_broadcast = dist.broadcast
    original_broadcast_object_list = dist.broadcast_object_list
    original_all_gather_object = dist.all_gather_object
    original_gather_object = dist.gather_object
    original_scatter_object_list = dist.scatter_object_list
    collective_seen = False

    def gpu_broadcast(tensor, *args, **kwargs):
        nonlocal collective_seen
        if not torch.is_tensor(tensor) or not tensor.is_cuda:
            raise TargetInvariantFailure(
                "sampled_tokens_left_gpu",
                "sampled tokens left the GPU before the PP transfer",
            )
        result = original_broadcast(tensor, *args, **kwargs)
        CALL_COUNTS["gpu_broadcasts"] += 1
        collective_seen = True
        return result

    def reject_object_collective(*args, **kwargs):
        raise TargetInvariantFailure(
            "object_collective_forbidden",
            "Python/object collective used for sampled tokens",
        )

    dist.broadcast = gpu_broadcast
    dist.broadcast_object_list = reject_object_collective
    dist.all_gather_object = reject_object_collective
    dist.gather_object = reject_object_collective
    dist.scatter_object_list = reject_object_collective
    try:
        observer = HandoffObserver()
        with observer.observe():
            CALL_COUNTS["sample_tokens_calls"] += 1
            output = GPUModelRunner.sample_tokens(runner, None)
        print(json.dumps({"handoff_observation": {
            "transfers": observer.transfers, "violations": observer.violations,
        }}, sort_keys=True), flush=True)
        if observer.violations:
            raise TargetInvariantFailure(
                "gpu_cpu_handoff_sync",
                f"Device-to-host transfer or host wait in handoff: {observer.violations}",
            )
    finally:
        dist.broadcast = original_broadcast
        dist.broadcast_object_list = original_broadcast_object_list
        dist.all_gather_object = original_all_gather_object
        dist.gather_object = original_gather_object
        dist.scatter_object_list = original_scatter_object_list
    if not collective_seen:
        raise TargetInvariantFailure(
            "no_gpu_broadcast",
            "production sample_tokens lifecycle did not use a GPU broadcast",
        )
    return output


def run_scenario(rank, tokens, req_ids, discard_mask, prior_outputs):
    if rank == 1:
        sampled = torch.tensor(tokens, dtype=torch.int32, device="cuda").reshape(-1, 1)
        runner = make_runner(req_ids, discard_mask, prior_outputs, sampled)
        CALL_COUNTS["execute_model_calls"] += 1
        output = invoke_production_sample(runner, is_sender=True)
        if runner.execute_model_state is not None or output is None:
            raise TargetInvariantFailure("sender_incomplete_return",
                                         "production sample_tokens did not finish")
        SENDER_LIFECYCLE["production_returned"] = True
        # Materialize the real async output AFTER the GPU handoff has finished.
        model_output = output.get_output() if hasattr(output, "get_output") else output
        expected = [[token] if not discard_mask[i] else []
                    for i, token in enumerate(tokens)]
        if model_output.req_ids != req_ids or model_output.sampled_token_ids != expected:
            raise TargetInvariantFailure("sender_output_mismatch",
                                         str(model_output.sampled_token_ids))
        for i, req_id in enumerate(req_ids):
            wanted = list(prior_outputs[req_id]) + ([] if discard_mask[i] else [-1])
            if runner.requests[req_id].output_token_ids != wanted:
                raise TargetInvariantFailure("sender_cached_state_mismatch", req_id)
        SENDER_LIFECYCLE["downstream_consumed"] = True
        return {"sent": sampled.cpu().flatten().tolist(),
                "sampled_output": model_output.sampled_token_ids,
                "sender_lifecycle": dict(SENDER_LIFECYCLE)}

    runner = receiver_runner(req_ids, discard_mask, prior_outputs)
    CALL_COUNTS["execute_model_calls"] += 1
    output = invoke_production_sample(runner, is_sender=False)
    if output is not None:
        raise TargetInvariantFailure(
            "receiver_produced_output",
            "receiver rank unexpectedly produced a model output",
        )
    SENDER_LIFECYCLE["production_returned"] = True
    received = runner.input_batch.prev_sampled_token_ids
    if received is None or not received.is_cuda:
        raise TargetInvariantFailure(
            "receiver_missing_gpu_tokens",
            "receiver did not rebuild prev_sampled_token_ids on the GPU",
        )
    if received.cpu().flatten().tolist() != tokens:
        raise TargetInvariantFailure(
            "received_tokens_mismatch",
            f"received {received.cpu().flatten().tolist()} != sent {tokens}",
        )
    expected_mapping = {
        req_id: index
        for index, req_id in enumerate(req_ids)
        if not discard_mask[index]
    }
    if runner.input_batch.prev_req_id_to_index != expected_mapping:
        raise TargetInvariantFailure(
            "req_id_mapping_mismatch",
            f"{runner.input_batch.prev_req_id_to_index} != {expected_mapping}",
        )
    for index, req_id in enumerate(req_ids):
        expected = list(prior_outputs[req_id])
        if not discard_mask[index]:
            expected.append(-1)
        if runner.requests[req_id].output_token_ids != expected:
            raise TargetInvariantFailure(
                "output_token_ids_mismatch",
                f"{req_id}: {runner.requests[req_id].output_token_ids} != {expected}",
            )
    next_order = list(reversed(expected_mapping))
    consumed = next_inputs(runner, next_order)
    expected_next = [tokens[expected_mapping[r]] for r in next_order]
    if consumed != expected_next:
        raise TargetInvariantFailure("next_input_tokens_mismatch",
                                     f"{consumed} != {expected_next}")
    SENDER_LIFECYCLE["downstream_consumed"] = True
    return {
        "next_input_ids": consumed,
        "mapping": expected_mapping,
        "received": tokens,
        "discarded": [
            req_id for index, req_id in enumerate(req_ids) if discard_mask[index]
        ],
    }


def run_integrated_scheduler_receiver(tokens):
    """Exercise NCCL receive and the next Scheduler round as adjacent stages.

    Worker cached request state and Scheduler requests are intentionally
    different production object types in this reduced integration.  The test
    therefore checks shared request identities and downstream state effects,
    not Python object identity across process-boundary abstractions.
    """

    scheduler = create_scheduler(
        model=LOCAL_MODEL_CONFIG,
        async_scheduling=True,
        pipeline_parallel_size=2,
        skip_tokenizer_init=True,
    )
    requests = create_requests(num_requests=len(tokens), num_tokens=8)
    for request in requests:
        scheduler.add_request(request)
    first = scheduler.schedule()
    req_ids = [request.request_id for request in requests]
    if set(first.num_scheduled_tokens) != set(req_ids):
        raise TargetInvariantFailure(
            "integrated_first_round_mismatch",
            f"{sorted(first.num_scheduled_tokens)} != {sorted(req_ids)}",
        )
    placeholders_before = {
        request.request_id: request.num_output_placeholders
        for request in requests
    }
    if not all(value > 0 for value in placeholders_before.values()):
        raise TargetInvariantFailure(
            "integrated_missing_output_placeholders",
            f"expected positive output placeholders, got {placeholders_before}",
        )

    runner = receiver_runner(
        req_ids,
        [False] * len(req_ids),
        {request.request_id: list(request.output_token_ids) for request in requests},
    )
    # NOTE: runner.requests already populated by receiver_runner() with
    # production CachedRequestState objects (mutable output_token_ids).
    # Do NOT replace with Scheduler's Request objects (ConstantList output_token_ids).
    CALL_COUNTS["execute_model_calls"] += 1
    output = invoke_production_sample(runner, is_sender=False)
    if output is not None:
        raise TargetInvariantFailure(
            "integrated_receiver_produced_output",
            "receiver rank unexpectedly produced a model output",
        )
    SENDER_LIFECYCLE["production_returned"] = True
    received = runner.input_batch.prev_sampled_token_ids
    if received is None or not received.is_cuda:
        raise TargetInvariantFailure(
            "integrated_receiver_missing_gpu_tokens",
            "receiver did not rebuild prev_sampled_token_ids on the GPU",
        )
    if received.cpu().flatten().tolist() != tokens:
        raise TargetInvariantFailure(
            "integrated_received_tokens_mismatch",
            f"received {received.cpu().flatten().tolist()} != sent {tokens}",
        )
    # Verify worker-side cached state got the placeholder append
    for req_id in req_ids:
        if runner.requests[req_id].output_token_ids[-1:] != [-1]:
            raise TargetInvariantFailure(
                "integrated_missing_placeholder_append",
                f"{req_id}: {runner.requests[req_id].output_token_ids[-1:]} != [-1]",
            )

    second = scheduler.schedule()
    if set(second.num_scheduled_tokens) != set(req_ids):
        raise TargetInvariantFailure(
            "integrated_next_round_mismatch",
            f"{sorted(second.num_scheduled_tokens)} != {sorted(req_ids)}",
        )
    consumed = next_inputs(runner, req_ids, scheduler_output=second)
    if consumed != tokens:
        raise TargetInvariantFailure("integrated_next_input_tokens_mismatch",
                                     f"{consumed} != {tokens}")
    SENDER_LIFECYCLE["downstream_consumed"] = True
    return {
        "next_input_ids": consumed,
        "request_ids": req_ids,
        "same_request_ids_across_stages": True,
        "same_python_request_objects": False,
        "integration_boundary": "worker cached-state receive + scheduler re-entry",
        "next_round_scheduled_ids": sorted(second.num_scheduled_tokens),
        "output_placeholders_before_receive": placeholders_before,
    }


SCENARIOS = {
    "basic": {
        "tokens": [101, 202],
        "req_ids": ["keep", "discard"],
        "discard_mask": [False, True],
        "prior_outputs": {"keep": [7], "discard": [9]},
    },
    "reordered": {
        "tokens": [303, 404, 505],
        "req_ids": ["third", "keep", "discard"],
        "discard_mask": [False, False, True],
        "prior_outputs": {"third": [], "keep": [7], "discard": [9]},
    },
    "integrated": {
        "tokens": [606, 707, 808],
        "req_ids": ["unused-0", "unused-1", "unused-2"],
        "discard_mask": [False, False, False],
        "prior_outputs": {"unused-0": [], "unused-1": [], "unused-2": []},
    },
}


def run_rank(scenario_name: str) -> int:
    # RANK/LOCAL_RANK/WORLD_SIZE/MASTER_ADDR/MASTER_PORT are assigned by the
    # trusted supervisor, one child per rank, each on its own stdout pipe. There
    # is no torchrun launcher here: rank identity belongs to the parent, and this
    # process must not be able to present itself as a different rank.
    local_rank = int(os.environ["LOCAL_RANK"])
    assigned_rank = int(os.environ["RANK"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl", timeout=timedelta(seconds=120))
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    assert world_size == 2
    # The collective's view of this process must match what the parent assigned.
    assert rank == assigned_rank, (
        f"rank mismatch: collective says {rank}, parent assigned {assigned_rank}"
    )

    group = pp_group(rank, world_size)
    scenario = SCENARIOS[scenario_name]
    original_get_pp_group = runner_module.get_pp_group
    runner_module.get_pp_group = lambda: group

    failure: TargetInvariantFailure | None = None
    record: dict = {}
    try:
        try:
            if scenario_name == "integrated" and rank == 0:
                record = run_integrated_scheduler_receiver(scenario["tokens"])
            else:
                record = run_scenario(
                    rank,
                    scenario["tokens"],
                    scenario["req_ids"],
                    scenario["discard_mask"],
                    scenario["prior_outputs"],
                )
        except TargetInvariantFailure as exc:
            failure = exc
        except Exception as exc:  # noqa: BLE001 - fail closed on any infra error
            # An unclassified error (missing fixture attribute, AttributeError,
            # KeyError, NCCL/CUDA error, ...) is NOT a valid contract failure.
            # Print a distinct infra marker (never a PASS) and exit non-zero so
            # the harness scores 0 for an infrastructure reason, not a target
            # reason. We do not enter the cross-rank agreement collective here
            # because the peer's state is unknown.
            print(
                json.dumps(
                    {
                        "verdict": "INFRA_ERROR",
                        "scenario": scenario_name,
                        "rank": rank,
                        "error_type": type(exc).__name__,
                        "detail": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            print("ASYNC_PP_INFRA_ERROR", flush=True)
            runner_module.get_pp_group = original_get_pp_group
            os._exit(2)
    finally:
        runner_module.get_pp_group = original_get_pp_group

    # Agree on a typed failure across ranks via a GPU collective (no CPU/object
    # path). Both ranks always reach here in the typed-failure and success cases.
    flag = torch.tensor([1.0 if failure is not None else 0.0], device="cuda")
    dist.all_reduce(flag, op=dist.ReduceOp.MAX)
    any_failure = flag.item() > 0.5

    if any_failure:
        if rank == 0:
            if failure is not None:
                reason, detail = failure.code, failure.detail
            else:
                reason = "peer_rank_invariant_failure"
                detail = "a peer rank raised a target invariant failure"
            print(
                json.dumps(
                    {
                        "verdict": "FAIL",
                        "reason_code": reason,
                        "detail": detail,
                        "scenario": scenario_name,
                        "world_size": world_size,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            print(f"ASYNC_PP_NCCL_SCENARIO=FAIL name={scenario_name}", flush=True)
        dist.barrier()
        dist.destroy_process_group()
        return 1

    # Test cleanup is separate from observed production completion.
    torch.cuda.synchronize()
    dist.barrier()
    SENDER_LIFECYCLE["barrier"] = True
    if rank == 0:
        props = torch.cuda.get_device_properties(local_rank)
        print(
            json.dumps(
                {
                    "gpu": props.name,
                    "private_helper_names_scored": False,
                    "production_entrypoint": "GPUModelRunner.execute_model -> GPUModelRunner.sample_tokens",
                    "scenario": scenario_name,
                    "scenario_result": record,
                    "world_size": world_size,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        print(f"ASYNC_PP_NCCL_SCENARIO=PASS name={scenario_name}", flush=True)
    # EVERY required rank emits its own framed payload. The supervisor requires
    # exactly one frame from rank 0 and one from rank 1, so a silent rank, a
    # dropped rank or a duplicated rank leaves the stage unsatisfied.
    lifecycle = dict(SENDER_LIFECYCLE)
    lifecycle["final_report"] = True
    emit_frame(
        {
            "scenario": scenario_name,
            "gpu_collective_seen": True,
            "world_size": world_size,
            "scenario_result": record,
            "sender_lifecycle": lifecycle,
            # Digest over the tokens this rank really handled.
            "payload_digest": payload_digest(STAGE, scenario["tokens"]),
        }
    )
    dist.destroy_process_group()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--check-scheduler", action="store_true")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args()
    assert_privilege_dropped()
    # Single-process stages: classify a target-invariant failure (reward 0 for a
    # target reason) distinctly from an infra crash (fail closed, no PASS).
    if args.check_config or args.check_scheduler:
        try:
            if args.check_config:
                return check_config()
            return check_scheduler_reentry()
        except TargetInvariantFailure as exc:
            print(
                json.dumps(
                    {"verdict": "FAIL", "reason_code": exc.code, "detail": exc.detail},
                    sort_keys=True,
                ),
                flush=True,
            )
            stage = "CONFIG" if args.check_config else "SCHEDULER_REENTRY"
            print(f"ASYNC_PP_{stage}=FAIL", flush=True)
            return 1
        except Exception as exc:  # noqa: BLE001 - fail closed
            print(
                json.dumps(
                    {
                        "verdict": "INFRA_ERROR",
                        "error_type": type(exc).__name__,
                        "detail": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            print("ASYNC_PP_INFRA_ERROR", flush=True)
            return 2
    if args.scenario is None:
        parser.error("--scenario is required for the distributed NCCL stage")
    return run_rank(args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
