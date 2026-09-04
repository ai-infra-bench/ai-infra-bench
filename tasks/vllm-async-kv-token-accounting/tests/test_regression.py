from __future__ import annotations

import pytest

from vllm.v1.request import RequestStatus

from verifier_support import (
    empty_output,
    make_request,
    make_scheduler,
    make_worker,
    sampled_output,
    start_worker_transfer,
    tiny_model,
    tokens,
    wait_for_worker_output,
)


def _start(tmp_path, cases, *, block_size=16, **plan):
    matches = {request_id: matched for request_id, _, matched in cases}
    scheduler, config, cache_config = make_scheduler(
        tiny_model(tmp_path / f"model-{block_size}"),
        block_size=block_size,
        matches=matches,
        **plan,
    )
    requests = []
    for index, (request_id, prompt_tokens, _matched) in enumerate(cases):
        request = make_request(
            request_id,
            tokens(prompt_tokens, salt=31 * (index + 1)),
            block_size=block_size,
        )
        scheduler.add_request(request)
        requests.append(request)
    initial = scheduler.schedule()
    return scheduler, config, cache_config, requests, initial


def _finish_transfer(scheduler, config, cache_config, initial):
    worker = make_worker(config, cache_config)
    try:
        start_worker_transfer(worker, initial)
        scheduler.update_from_output(initial, empty_output())
        waiting = scheduler.schedule()
        completion = wait_for_worker_output(worker)
        scheduler.update_from_output(waiting, empty_output(completion))
        return scheduler.schedule(), worker.completed_checksums
    finally:
        worker.shutdown()


def _assert_ready(output, expected):
    by_id = {item.req_id: item for item in output.scheduled_new_reqs}
    assert set(by_id) == set(expected)
    assert set(output.num_scheduled_tokens) == set(expected)
    for request_id, (computed, scheduled) in expected.items():
        assert by_id[request_id].num_computed_tokens == computed
        assert output.num_scheduled_tokens[request_id] == scheduled


@pytest.mark.parametrize(
    ("block_size", "prompt_tokens", "matched_tokens"),
    [
        (8, 43, 1),
        (8, 43, 11),
        (16, 67, 19),
        (16, 70, 37),
        (16, 70, 69),
        (32, 95, 47),
        (32, 129, 65),
    ],
)
def test_partial_async_hits_reach_runner_exactly(
    tmp_path, block_size, prompt_tokens, matched_tokens
):
    case = ("partial", prompt_tokens, matched_tokens)
    scheduler, config, cache_config, requests, initial = _start(
        tmp_path, [case], block_size=block_size
    )
    assert not initial.num_scheduled_tokens
    assert requests[0].status == RequestStatus.WAITING_FOR_REMOTE_KVS

    ready, checksums = _finish_transfer(scheduler, config, cache_config, initial)

    _assert_ready(
        ready,
        {"partial": (matched_tokens, prompt_tokens - matched_tokens)},
    )
    assert set(checksums) == {"partial"}


def test_concurrent_transfers_complete_independently(tmp_path):
    cases = [
        ("short", 53, 5),
        ("medium", 67, 19),
        ("long", 83, 41),
    ]
    scheduler, config, cache_config, _requests, initial = _start(
        tmp_path,
        cases,
        delays_ms={"short": 5, "medium": 35, "long": 70},
    )
    worker = make_worker(config, cache_config)
    try:
        start_worker_transfer(worker, initial)
        scheduler.update_from_output(initial, empty_output())
        observed = {}
        for _ in range(12):
            waiting = scheduler.schedule()
            completion = wait_for_worker_output(worker)
            scheduler.update_from_output(waiting, empty_output(completion))
            ready = scheduler.schedule()
            for item in ready.scheduled_new_reqs:
                observed[item.req_id] = (
                    item.num_computed_tokens,
                    ready.num_scheduled_tokens[item.req_id],
                )
            if ready.num_scheduled_tokens:
                scheduler.update_from_output(ready, sampled_output(ready))
            if len(observed) == len(cases):
                break
        assert observed == {
            request_id: (matched, prompt - matched)
            for request_id, prompt, matched in cases
        }
        assert set(worker.completed_checksums) == {case[0] for case in cases}
    finally:
        worker.shutdown()


@pytest.mark.parametrize(
    ("prompt_tokens", "matched_tokens"),
    [(43, 16), (67, 32), (95, 64)],
)
def test_block_aligned_async_hits_are_unchanged(
    tmp_path, prompt_tokens, matched_tokens
):
    case = ("aligned", prompt_tokens, matched_tokens)
    scheduler, config, cache_config, _requests, initial = _start(tmp_path, [case])
    ready, _ = _finish_transfer(scheduler, config, cache_config, initial)
    _assert_ready(
        ready,
        {"aligned": (matched_tokens, prompt_tokens - matched_tokens)},
    )


@pytest.mark.parametrize("prompt_tokens", [17, 64, 70, 127])
def test_full_prompt_hits_recompute_one_token(tmp_path, prompt_tokens):
    case = ("full", prompt_tokens, prompt_tokens)
    scheduler, config, cache_config, _requests, initial = _start(tmp_path, [case])
    ready, _ = _finish_transfer(scheduler, config, cache_config, initial)
    _assert_ready(ready, {"full": (prompt_tokens - 1, 1)})


def test_zero_hit_runs_without_async_wait(tmp_path):
    _scheduler, _config, _cache, requests, output = _start(
        tmp_path, [("cold", 73, 0)]
    )
    _assert_ready(output, {"cold": (0, 73)})
    assert requests[0].status == RequestStatus.RUNNING


@pytest.mark.parametrize("matched_tokens", [11, 32])
def test_synchronous_connector_path_is_unchanged(tmp_path, matched_tokens):
    prompt_tokens = 70
    _scheduler, _config, _cache, requests, output = _start(
        tmp_path,
        [("sync", prompt_tokens, matched_tokens)],
        sync_request_ids=["sync"],
    )
    _assert_ready(output, {"sync": (matched_tokens, prompt_tokens - matched_tokens)})
    assert requests[0].status == RequestStatus.RUNNING


@pytest.mark.parametrize(
    ("matched_tokens", "failed_block", "expected_computed"),
    [(37, 0, 0), (53, 1, 16), (69, 2, 32)],
)
def test_failed_async_blocks_fall_back_to_recomputation(
    tmp_path, matched_tokens, failed_block, expected_computed
):
    prompt_tokens = 86
    scheduler, config, cache_config, _requests, initial = _start(
        tmp_path,
        [("failure", prompt_tokens, matched_tokens)],
        failure_block_index={"failure": failed_block},
    )
    ready, _ = _finish_transfer(scheduler, config, cache_config, initial)
    _assert_ready(
        ready,
        {"failure": (expected_computed, prompt_tokens - expected_computed)},
    )


def test_partial_transfer_only_exposes_complete_prefix_blocks(tmp_path):
    prompt = tokens(70, salt=101)
    scheduler, config, cache_config = make_scheduler(
        tiny_model(tmp_path / "prefix-model"),
        block_size=16,
        num_blocks=5,
        matches={"leader": 37, "follower": 0},
    )
    scheduler.add_request(make_request("leader", prompt, block_size=16))
    initial = scheduler.schedule()
    worker = make_worker(config, cache_config)
    try:
        start_worker_transfer(worker, initial)
        scheduler.update_from_output(initial, empty_output())
        waiting = scheduler.schedule()
        scheduler.update_from_output(
            waiting,
            empty_output(wait_for_worker_output(worker)),
        )
        # There is only one free block after the transfer.  The original
        # request cannot allocate its remaining prompt, so this scheduling
        # pass commits only the externally loaded prefix and stays idle.
        assert not scheduler.schedule().num_scheduled_tokens
        scheduler.finish_requests("leader", RequestStatus.FINISHED_ABORTED)

        follower_prompt = prompt[:49]
        scheduler.add_request(
            make_request("follower", follower_prompt, block_size=16)
        )
        ready = scheduler.schedule()
        by_id = {item.req_id: item for item in ready.scheduled_new_reqs}
        assert by_id["follower"].num_computed_tokens == 32
        assert ready.num_scheduled_tokens["follower"] == 17
    finally:
        worker.shutdown()


def test_local_and_external_prefixes_combine_without_rounding(tmp_path):
    block_size = 16
    shared = tokens(32, salt=211)
    seed_tokens = shared + tokens(17, salt=301)
    target_tokens = shared + tokens(51, salt=401)
    scheduler, _config, _cache = make_scheduler(
        tiny_model(tmp_path / "local-model"),
        block_size=block_size,
        matches={"seed": 0, "target": 9},
    )
    scheduler.add_request(make_request("seed", seed_tokens, block_size=block_size))
    seed_output = scheduler.schedule()
    scheduler.update_from_output(seed_output, sampled_output(seed_output))

    scheduler.add_request(make_request("target", target_tokens, block_size=block_size))
    initial = scheduler.schedule()
    assert not initial.num_scheduled_tokens
    config = scheduler.vllm_config
    cache_config = scheduler.kv_cache_config
    ready, _ = _finish_transfer(scheduler, config, cache_config, initial)
    _assert_ready(ready, {"target": (41, len(target_tokens) - 41)})


def test_cancelled_transfer_does_not_block_later_requests(tmp_path):
    scheduler, config, cache_config, _requests, initial = _start(
        tmp_path,
        [("cancelled", 70, 37)],
        delays_ms={"cancelled": 40},
    )
    worker = make_worker(config, cache_config)
    try:
        start_worker_transfer(worker, initial)
        scheduler.update_from_output(initial, empty_output())
        scheduler.finish_requests("cancelled", RequestStatus.FINISHED_ABORTED)
        waiting = scheduler.schedule()
        scheduler.update_from_output(
            waiting,
            empty_output(wait_for_worker_output(worker)),
        )

        scheduler.add_request(
            make_request("after-cancel", tokens(55, salt=997), block_size=16)
        )
        ready = scheduler.schedule()
        _assert_ready(ready, {"after-cancel": (0, 55)})
    finally:
        worker.shutdown()
