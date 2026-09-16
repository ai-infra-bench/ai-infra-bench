#!/usr/bin/env python3
"""Independent fresh challenge for async-PP sampled-token handoff (2-rank NCCL).

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. Launch under torchrun with 2 ranks on the
built A100 image:

    torchrun --nproc_per_node=2 challenge_token_handoff.py

It re-enters the production lifecycle (GPUModelRunner.sample_tokens with a
real NCCL PP group) but re-derives the handoff invariants on a FRESH scenario
distinct from the verifier's basic/reordered/integrated:

  * 5 requests, discards interleaved at positions 1 and 3 (verifier only ever
    discards a trailing request), req_ids reordered, all with non-empty prior
    outputs, fresh token ids.

Invariants re-derived (not copied from the verifier body):
  1. Sampled tokens cross the PP boundary via a GPU (is_cuda) collective;
     every object/CPU collective (broadcast_tensor_dict, *_object) is forbidden.
  2. No blocking GPU->CPU transfer, CUDA scalar read or host wait occurs.
  3. Receiver rebuilds prev_sampled_token_ids on-GPU matching sent tokens.
  4. prev_req_id_to_index maps exactly the kept (non-discarded) requests to
     their ORIGINAL positional index.
  5. Kept requests get a -1 placeholder appended to output_token_ids;
     discarded requests are left unchanged.

Failure model (fail-closed, machine-checkable per README contract):
  * Every invariant this challenge OWNS is signalled by raising the typed
    ``ChallengeInvariantFailure(code, detail)``. When any rank raises one, the
    ranks agree via a GPU all-reduce, rank0 emits a structured JSON record and
    exactly one ``CHALLENGE_TOKEN_HANDOFF=FAIL`` line (flushed BEFORE the
    barrier so a fast peer exit cannot make torchrun kill rank0 and drop the
    marker), and both ranks exit non-zero.
  * Any OTHER exception (import, CUDA, NCCL, a missing fixture attribute, ...)
    propagates untyped: no FAIL marker is printed, so the harness classifies it
    as an infrastructure failure rather than a valid control outcome. This is
    deliberate -- a generic "crashed" signal must NOT be accepted as evidence
    that the implementation failed the behavioral contract.

Phase D runs this against Oracle (PASS) and a semantically-different correct
alternative (PASS); Base and the incorrect/perf-only controls must emit exactly
one CHALLENGE_TOKEN_HANDOFF=FAIL with a typed reason_code.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import torch
import torch.distributed as dist

import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.v1.worker.gpu_model_runner import GPUModelRunner

# Fresh scenario: interleaved discards, reordered ids, all non-empty priors.
TOKENS = [111, 222, 333, 444, 555]
REQ_IDS = ["r-c", "r-a", "r-e", "r-b", "r-d"]
DISCARD_MASK = [False, True, False, True, False]
PRIOR_OUTPUTS = {
    "r-c": [3],
    "r-a": [5, 6],
    "r-e": [7],
    "r-b": [9, 10, 11],
    "r-d": [13],
}


# The curator runner mounts task-owned constructors read-only. They contain no
# expected outputs; this challenge derives its own input and output invariants.
from pathlib import Path
fixture_dirs = [Path("/mnt/tests-ro"), Path("/tests")]
source_parents = Path(__file__).resolve().parents
if len(source_parents) > 2:
    fixture_dirs.append(source_parents[2] / "tests")
for fixture_dir in fixture_dirs:
    if (fixture_dir / "worker_fixtures.py").is_file():
        sys.path.insert(0, str(fixture_dir))
        break
from worker_fixtures import make_runner, next_inputs
from handoff_observer import HandoffObserver


class ChallengeInvariantFailure(RuntimeError):
    """A handoff invariant this challenge OWNS was violated.

    Distinct from arbitrary runtime errors: only this type is accepted as a
    valid control failure and lowered to a CHALLENGE_TOKEN_HANDOFF=FAIL marker.
    """

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")





CHALLENGE_NONCE = os.environ.get("CHALLENGE_NONCE", "")
CHALLENGE_SCENARIO = os.environ.get("CHALLENGE_SCENARIO", "")
if CHALLENGE_SCENARIO == "fresh-interleaved-discard-7req":
    TOKENS = [617, 29, 881, 43, 509, 71, 997]
    REQ_IDS = ["u-f", "u-b", "u-g", "u-a", "u-e", "u-c", "u-d"]
    DISCARD_MASK = [False, True, False, False, True, False, True]
    PRIOR_OUTPUTS = {r: list(range(13, 13 + i % 3))
                     for i, r in enumerate(REQ_IDS)}



def emit_challenge_frame(payload: dict) -> None:
    """Single framed payload consumed by the external challenge wrapper.

    The wrapper mints the nonce per invocation, so a pre-planted or replayed
    payload cannot carry it, and a bare ``sys.exit(0)`` emits nothing at all.
    """
    body = dict(payload)
    body.setdefault("scenario", CHALLENGE_SCENARIO)
    body.setdefault("rank", int(os.environ.get("RANK", "0")))
    body["scenario_completed"] = True
    print(
        f"##CHALLENGE_PAYLOAD {CHALLENGE_NONCE} "
        + json.dumps(body, sort_keys=True)
        + " ##END",
        flush=True,
    )


def pp_group(rank: int, world_size: int):
    from worker_fixtures import initialize_runner_groups
    return initialize_runner_groups(rank, world_size)


def receiver_runner():
    return make_runner(REQ_IDS, DISCARD_MASK, PRIOR_OUTPUTS)



def invoke_production_sample(runner, *, is_sender: bool):
    orig_broadcast = dist.broadcast
    orig_object_list = dist.broadcast_object_list
    orig_all_gather = dist.all_gather_object
    orig_gather = dist.gather_object
    orig_scatter = dist.scatter_object_list
    collective_seen = False

    def gpu_broadcast(tensor, *args, **kwargs):
        nonlocal collective_seen
        if not torch.is_tensor(tensor) or not tensor.is_cuda:
            raise ChallengeInvariantFailure(
                "sampled_tokens_left_gpu",
                "sampled tokens left the GPU before the PP transfer",
            )
        result = orig_broadcast(tensor, *args, **kwargs)
        collective_seen = True
        return result

    def reject_object(*args, **kwargs):
        raise ChallengeInvariantFailure(
            "object_collective_forbidden",
            "Python/object collective used for sampled tokens",
        )

    dist.broadcast = gpu_broadcast
    dist.broadcast_object_list = reject_object
    dist.all_gather_object = reject_object
    dist.gather_object = reject_object
    dist.scatter_object_list = reject_object
    try:
        observer = HandoffObserver()
        with observer.observe():
            output = GPUModelRunner.sample_tokens(runner, None)
        print(json.dumps({"handoff_observation": {
            "transfers": observer.transfers, "violations": observer.violations,
        }}, sort_keys=True), flush=True)
        if observer.violations:
            raise ChallengeInvariantFailure(
                "gpu_cpu_handoff_sync",
                f"Device-to-host transfer or host wait in handoff: {observer.violations}",
            )
    finally:
        dist.broadcast = orig_broadcast
        dist.broadcast_object_list = orig_object_list
        dist.all_gather_object = orig_all_gather
        dist.gather_object = orig_gather
        dist.scatter_object_list = orig_scatter
    if not collective_seen:
        raise ChallengeInvariantFailure(
            "no_gpu_broadcast",
            "production lifecycle did not use a GPU broadcast for handoff",
        )
    return output


def _run_scenario(rank: int) -> dict:
    """Drive one rank through the production handoff. Returns the record dict.

    Raises ChallengeInvariantFailure for any owned-invariant violation.
    """
    if rank == 1:
        sampled = torch.tensor(
            TOKENS, dtype=torch.int32, device="cuda"
        ).reshape(-1, 1)
        runner = make_runner(REQ_IDS, DISCARD_MASK, PRIOR_OUTPUTS, sampled)
        output = invoke_production_sample(runner, is_sender=True)
        if output is None or runner.execute_model_state is not None:
            raise ChallengeInvariantFailure("sender_incomplete", "production return missing")
        concrete = output.get_output() if hasattr(output, "get_output") else output
        expected = [[token] if not DISCARD_MASK[i] else []
                    for i, token in enumerate(TOKENS)]
        if concrete.req_ids != REQ_IDS or concrete.sampled_token_ids != expected:
            raise ChallengeInvariantFailure("sender_output_mismatch", str(concrete))
        return {"sent": sampled.cpu().flatten().tolist(),
                "sampled_output": concrete.sampled_token_ids}

    runner = receiver_runner()
    output = invoke_production_sample(runner, is_sender=False)
    if output is not None:
        raise ChallengeInvariantFailure(
            "receiver_produced_output",
            "receiver rank unexpectedly produced a model output",
        )
    received = runner.input_batch.prev_sampled_token_ids
    if received is None or not received.is_cuda:
        raise ChallengeInvariantFailure(
            "receiver_missing_gpu_tokens",
            "receiver did not rebuild prev_sampled_token_ids on the GPU",
        )
    if received.cpu().flatten().tolist() != TOKENS:
        raise ChallengeInvariantFailure(
            "received_tokens_mismatch",
            f"received {received.cpu().flatten().tolist()} != sent {TOKENS}",
        )
    expected_mapping = {
        req_id: index
        for index, req_id in enumerate(REQ_IDS)
        if not DISCARD_MASK[index]
    }
    if runner.input_batch.prev_req_id_to_index != expected_mapping:
        raise ChallengeInvariantFailure(
            "req_id_mapping_mismatch",
            f"{runner.input_batch.prev_req_id_to_index} != {expected_mapping}",
        )
    for index, req_id in enumerate(REQ_IDS):
        expected = list(PRIOR_OUTPUTS[req_id])
        if not DISCARD_MASK[index]:
            expected.append(-1)
        if runner.requests[req_id].output_token_ids != expected:
            raise ChallengeInvariantFailure(
                "output_token_ids_mismatch",
                f"{req_id}: {runner.requests[req_id].output_token_ids} != {expected}",
            )
    next_order = list(reversed(expected_mapping))
    consumed = next_inputs(runner, next_order)
    wanted = [TOKENS[expected_mapping[r]] for r in next_order]
    if consumed != wanted:
        raise ChallengeInvariantFailure("next_input_mismatch", f"{consumed} != {wanted}")
    return {
        "next_input_ids": consumed,
        "received": TOKENS,
        "mapping": expected_mapping,
        "discarded": [r for i, r in enumerate(REQ_IDS) if DISCARD_MASK[i]],
    }


def run_rank() -> int:
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl", timeout=timedelta(seconds=120))
    rank = dist.get_rank()
    world_size = dist.get_world_size()
    assert world_size == 2, "challenge requires exactly 2 ranks"

    group = pp_group(rank, world_size)
    original_get_pp_group = runner_module.get_pp_group
    runner_module.get_pp_group = lambda: group

    failure: ChallengeInvariantFailure | None = None
    record: dict = {}
    try:
        try:
            record = _run_scenario(rank)
        except ChallengeInvariantFailure as exc:
            failure = exc
    finally:
        runner_module.get_pp_group = original_get_pp_group

    # Agree on failure across ranks via a GPU collective (no CPU/object path).
    flag = torch.tensor(
        [1.0 if failure is not None else 0.0], device="cuda"
    )
    dist.all_reduce(flag, op=dist.ReduceOp.MAX)
    any_failure = flag.item() > 0.5

    if any_failure:
        # rank0 owns the marker. Prefer its own typed reason; if only the peer
        # failed, report that explicitly. Print+flush BEFORE the barrier.
        if rank == 0:
            if failure is not None:
                reason, detail = failure.code, failure.detail
            else:
                reason = "peer_rank_invariant_failure"
                detail = "a peer rank raised a challenge invariant failure"
            print(json.dumps({
                "verdict": "FAIL",
                "reason_code": reason,
                "detail": detail,
                "scenario": CHALLENGE_SCENARIO or "fresh-interleaved-discard-5req",
                "world_size": world_size,
            }, sort_keys=True), flush=True)
            print("CHALLENGE_TOKEN_HANDOFF=FAIL", flush=True)
        dist.barrier()
        dist.destroy_process_group()
        return 1

    dist.barrier()
    if rank == 0:
        print(json.dumps({
            "gpu": torch.cuda.get_device_properties(local_rank).name,
            "production_entrypoint": "GPUModelRunner.sample_tokens",
            "scenario": CHALLENGE_SCENARIO or "fresh-interleaved-discard-5req",
            "scenario_result": record,
            "verdict": "PASS",
            "world_size": world_size,
        }, sort_keys=True), flush=True)
        print("CHALLENGE_TOKEN_HANDOFF=PASS", flush=True)
    # Every required rank reports, so a silent/dropped/duplicated rank leaves the
    # scenario unsatisfied in the wrapper's manifest.
    # Serialize reports after rank 0's summary: print() may write its text and
    # newline separately, so simultaneous ranks can otherwise merge two lines.
    # These barriers are outside the observed production handoff.
    dist.barrier()
    for reporting_rank in range(world_size):
        if rank == reporting_rank:
            emit_challenge_frame(
                {
                    "scenario_result": record,
                    "world_size": world_size,
                    "gpu_collective_seen": True,
                }
            )
        dist.barrier()
    dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_rank())
