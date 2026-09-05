#!/usr/bin/env python3
"""Unprivileged raw-observation worker for request lifecycle behavior."""

from __future__ import annotations

import gc
import json
import sys
import weakref
from pathlib import Path

sys.path.insert(0, "/workspace/repo")

import vllm
from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
from vllm.sampling_params import SamplingParams
from vllm.utils.hashing import sha256
from vllm.v1.core.kv_cache_utils import get_request_block_hasher, init_none_hash
from vllm.v1.core.sched.request_queue import FCFSRequestQueue
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.request import Request, RequestStatus


RESULT_PREFIX = "AI_INFRA_OBSERVATION="


class LargeFeature:
    def __init__(self, marker: int):
        self.marker = marker
        self.data = bytearray(256 * 1024)


class FreeRecorder:
    def __init__(self) -> None:
        self.freed: list[str] = []

    def free(self, request: Request) -> None:
        self.freed.append(request.request_id)


def make_scheduler() -> Scheduler:
    scheduler = object.__new__(Scheduler)
    scheduler.requests = {}
    scheduler.waiting = FCFSRequestQueue()
    scheduler.running = []
    scheduler.log_stats = False
    scheduler.num_waiting_for_streaming_input = 0
    scheduler.finished_req_ids = set()
    scheduler.finished_req_ids_dict = None
    scheduler.finished_recving_kv_req_ids = set()
    scheduler.failed_recving_kv_req_ids = set()
    scheduler.connector = None
    scheduler.encoder_cache_manager = FreeRecorder()
    scheduler.kv_cache_manager = FreeRecorder()
    return scheduler


def production_hasher():
    init_none_hash(sha256)
    return get_request_block_hasher(4, sha256)


def make_request(
    request_id: str,
    *,
    resumable: bool = False,
    with_hasher: bool = True,
    tokens: list[int] | None = None,
) -> tuple[Request, LargeFeature]:
    feature = LargeFeature(hash(request_id))
    mm_feature = MultiModalFeatureSpec(
        data={"payload": feature},
        modality="image",
        identifier=f"feature-{request_id}",
        mm_position=PlaceholderRange(offset=0, length=4),
    )
    request = Request(
        request_id=request_id,
        prompt_token_ids=tokens or list(range(1, 9)),
        sampling_params=SamplingParams(max_tokens=8),
        pooling_params=None,
        eos_token_id=0,
        mm_features=[mm_feature],
        block_hasher=production_hasher() if with_hasher else None,
        resumable=resumable,
    )
    return request, feature


def refs_state(
    scheduler: Scheduler,
    request_id: str,
    request_ref: weakref.ReferenceType[Request],
    feature_ref: weakref.ReferenceType[LargeFeature],
) -> dict[str, bool]:
    return {
        "request_alive": request_ref() is not None,
        "feature_alive": feature_ref() is not None,
        "owned": request_id in scheduler.requests,
    }


def add_and_drop(
    scheduler: Scheduler, request: Request, feature: LargeFeature
) -> tuple[str, weakref.ReferenceType[Request], weakref.ReferenceType[LargeFeature]]:
    request_id = request.request_id
    request_ref = weakref.ref(request)
    feature_ref = weakref.ref(feature)
    scheduler.add_request(request)
    return request_id, request_ref, feature_ref


def finish_and_observe(status: RequestStatus, *, running: bool = False, hasher=True):
    scheduler = make_scheduler()
    request, feature = make_request("lifecycle", with_hasher=hasher)
    request_id, request_ref, feature_ref = add_and_drop(scheduler, request, feature)
    if running:
        scheduler.waiting.pop_request()
        request.status = RequestStatus.RUNNING
        scheduler.running.append(request)
    del request, feature
    scheduler.finish_requests(request_id, status)
    return refs_state(scheduler, request_id, request_ref, feature_ref)


def streaming_wait_or_end(*, end: bool):
    scheduler = make_scheduler()
    request, feature = make_request("stream", resumable=True)
    request_id, request_ref, feature_ref = add_and_drop(scheduler, request, feature)
    scheduler.waiting.pop_request()
    request.status = RequestStatus.FINISHED_STOPPED
    assert Scheduler._handle_stopped_request(scheduler, request) is False
    del request, feature
    if end:
        sentinel, _ = make_request("stream", resumable=False, with_hasher=False)
        scheduler.add_request(sentinel)
        del sentinel
    return refs_state(scheduler, request_id, request_ref, feature_ref)


def hash_observation(stage: str) -> dict[str, object]:
    scheduler = make_scheduler()
    request, _ = make_request("hash", resumable=True)
    sequences = [list(request.block_hashes)]
    if stage in {"append", "stream"}:
        request.append_output_token_ids([9, 10, 11, 12])
        sequences.append(list(request.block_hashes))
    if stage == "stream":
        scheduler.add_request(request)
        scheduler.waiting.pop_request()
        request.num_computed_tokens = request.num_tokens
        request.status = RequestStatus.FINISHED_STOPPED
        assert Scheduler._handle_stopped_request(scheduler, request) is False
        continuation, _ = make_request(
            "hash", resumable=True, with_hasher=False, tokens=[13, 14, 15, 16]
        )
        scheduler.add_request(continuation)
        sequences.append(list(request.block_hashes))
    prefixes_preserved = all(
        sequences[index][: len(sequences[index - 1])] == sequences[index - 1]
        for index in range(1, len(sequences))
    )
    final = sequences[-1]
    return {
        "counts": [len(sequence) for sequence in sequences],
        "prefixes_preserved": prefixes_preserved,
        "unique_hashes": len(set(final)),
    }


def observe(case: str) -> object:
    if case == "candidate_source":
        return str(Path(vllm.__file__).resolve())
    if case == "live_request_retained":
        scheduler = make_scheduler()
        request, feature = make_request("live")
        request_id, request_ref, feature_ref = add_and_drop(scheduler, request, feature)
        del request, feature
        return refs_state(scheduler, request_id, request_ref, feature_ref)
    if case == "normal_completion_releases":
        return finish_and_observe(RequestStatus.FINISHED_STOPPED, running=True)
    if case == "waiting_cancel_releases":
        return finish_and_observe(RequestStatus.FINISHED_ABORTED)
    if case == "running_cancel_releases":
        return finish_and_observe(RequestStatus.FINISHED_ABORTED, running=True)
    if case == "streaming_wait_retained":
        return streaming_wait_or_end(end=False)
    if case == "streaming_end_releases":
        return streaming_wait_or_end(end=True)
    if case == "initial_prefix_hashes":
        return hash_observation("initial")
    if case == "append_prefix_hashes":
        return hash_observation("append")
    if case == "streaming_continuation_hashes":
        return hash_observation("stream")
    if case == "no_prefix_cache_completion":
        return finish_and_observe(RequestStatus.FINISHED_STOPPED, hasher=False)
    raise ValueError(f"unknown case: {case}")


def main() -> int:
    request = json.loads(sys.stdin.readline())
    case = request["case"]
    nonce = request["nonce"]
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        value = observe(case)
        result = {"case": case, "nonce": nonce, "value": value, "error": None}
    except Exception as exc:
        result = {
            "case": case,
            "nonce": nonce,
            "value": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
