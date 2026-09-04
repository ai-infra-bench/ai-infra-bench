from __future__ import annotations

import threading

import pytest

from verifier_support import (
    assert_fresh_store_works,
    complete_transfer,
    make_harness,
    make_request,
    observed_hit,
    populate_cache,
    reset,
    start_load,
    start_store,
)


def _complete_after_gate(completion):
    gate = threading.Event()
    errors = []

    def run():
        gate.wait(timeout=10)
        try:
            completion()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return gate, thread, errors


def _assert_waits_then_succeeds(harness, completion):
    gate, thread, errors = _complete_after_gate(completion)
    assert reset(harness) is False
    assert reset(harness) is False
    gate.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors
    assert reset(harness) is True


def _assert_transfer_owned_blocks_stay_reserved(pool, owned_block_ids):
    available = pool.get_new_blocks(pool.get_num_free_blocks())
    try:
        assert pool.get_num_free_blocks() == 0
        allocated_ids = {block.block_id for block in available}
        assert allocated_ids.isdisjoint(owned_block_ids)
        with pytest.raises(ValueError, match="Cannot get 1 free blocks"):
            pool.get_new_blocks(1)
    finally:
        pool.free_blocks(available)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("kind", ["store", "load"])
def test_reset_keeps_transfer_owned_blocks_unavailable_until_completion(
    tmp_path, lazy, kind
):
    harness = make_harness(
        tmp_path / f"ownership-{kind}-{lazy}",
        lazy=lazy,
        num_cpu_blocks=12,
        num_gpu_blocks=20,
    )
    source = make_request(
        f"ownership-{kind}-{lazy}", num_blocks=3, token_seed=90000
    )
    if kind == "store":
        transfer = start_store(harness, source, 3)
    else:
        populate_cache(harness, source, 3)
        _loading, transfer, _metadata = start_load(
            harness, source, f"ownership-load-{lazy}"
        )

    assert reset(harness) is False
    _assert_transfer_owned_blocks_stay_reserved(
        harness.gpu_pool, transfer.gpu_block_ids
    )
    _assert_transfer_owned_blocks_stay_reserved(
        harness.cpu_pool, transfer.cpu_block_ids
    )

    complete_transfer(harness, transfer)
    assert reset(harness) is True
    assert observed_hit(harness, source, f"ownership-old-{kind}-{lazy}")[0] == 0
    assert_fresh_store_works(harness, 95000 + int(lazy))


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 3], ids=["short", "long"])
def test_idle_reset_clears_old_entries_and_is_idempotent(
    tmp_path, lazy, num_blocks
):
    harness = make_harness(tmp_path / f"idle-{lazy}-{num_blocks}", lazy=lazy)
    source = make_request(
        f"idle-source-{lazy}-{num_blocks}",
        num_blocks=num_blocks,
        token_seed=1000 + num_blocks * 100,
    )
    populate_cache(harness, source, num_blocks)
    assert observed_hit(harness, source, "before-reset")[0] > 0
    assert reset(harness) is True
    assert observed_hit(harness, source, "after-reset")[0] == 0
    assert reset(harness) is True
    assert_fresh_store_works(harness, 5000 + num_blocks)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 2, 3], ids=["short", "medium", "long"])
def test_inflight_store_cannot_repopulate_reset_cache(
    tmp_path, lazy, num_blocks
):
    harness = make_harness(tmp_path / f"store-{lazy}-{num_blocks}", lazy=lazy)
    source = make_request(
        f"store-source-{lazy}-{num_blocks}",
        num_blocks=num_blocks,
        token_seed=10000 + num_blocks * 100,
    )
    transfer = start_store(harness, source, num_blocks)
    _assert_waits_then_succeeds(
        harness,
        lambda: complete_transfer(harness, transfer),
    )
    assert observed_hit(harness, source, "old-store")[0] == 0
    assert_fresh_store_works(harness, 15000 + num_blocks)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
@pytest.mark.parametrize("num_blocks", [1, 3], ids=["short", "long"])
def test_inflight_load_reset_recovers_and_clears_cache(
    tmp_path, lazy, num_blocks
):
    harness = make_harness(tmp_path / f"load-{lazy}-{num_blocks}", lazy=lazy)
    source = make_request(
        f"load-source-{lazy}-{num_blocks}",
        num_blocks=num_blocks,
        token_seed=20000 + num_blocks * 100,
    )
    populate_cache(harness, source, num_blocks)
    _loading, transfer, _metadata = start_load(
        harness, source, f"loading-{lazy}-{num_blocks}"
    )
    _assert_waits_then_succeeds(
        harness,
        lambda: complete_transfer(harness, transfer),
    )
    assert observed_hit(harness, source, "old-load")[0] == 0
    assert_fresh_store_works(harness, 25000 + num_blocks)


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
def test_reset_connector_false_leaves_offloaded_entries_visible(tmp_path, lazy):
    harness = make_harness(tmp_path / f"local-only-{lazy}", lazy=lazy)
    source = make_request(
        f"local-only-source-{lazy}",
        num_blocks=2,
        token_seed=30000,
    )
    populate_cache(harness, source, 2)
    assert reset(harness, reset_connector=False) is True
    assert observed_hit(harness, source, "connector-not-reset")[0] > 0
    assert reset(harness, reset_connector=True) is True
    assert observed_hit(harness, source, "connector-reset")[0] == 0


def test_multiple_store_completions_may_arrive_out_of_order(tmp_path):
    harness = make_harness(tmp_path / "out-of-order", lazy=False)
    first = make_request("store-first", num_blocks=2, token_seed=40000)
    second = make_request("store-second", num_blocks=3, token_seed=50000)
    first_transfer = start_store(harness, first, 2)
    second_transfer = start_store(harness, second, 3)
    assert reset(harness) is False
    complete_transfer(harness, second_transfer)
    assert reset(harness) is False
    complete_transfer(harness, first_transfer)
    assert reset(harness) is True
    assert observed_hit(harness, first, "first-old")[0] == 0
    assert observed_hit(harness, second, "second-old")[0] == 0


def test_partial_worker_store_completion_keeps_reset_pending(tmp_path):
    harness = make_harness(
        tmp_path / "partial-workers",
        lazy=False,
        worker_count=2,
    )
    source = make_request("partial-workers", num_blocks=2, token_seed=60000)
    transfer = start_store(harness, source, 2)
    assert reset(harness) is False
    complete_transfer(harness, transfer, count=1)
    assert reset(harness) is False
    complete_transfer(harness, transfer, count=1)
    assert reset(harness) is True
    assert observed_hit(harness, source, "partial-old")[0] == 0


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
def test_simultaneous_store_and_load_both_drain_before_success(tmp_path, lazy):
    harness = make_harness(tmp_path / f"mixed-{lazy}", lazy=lazy)
    cached = make_request(
        f"mixed-cached-{lazy}", num_blocks=2, token_seed=70000
    )
    populate_cache(harness, cached, 2)
    _loading, load_transfer, _metadata = start_load(
        harness, cached, f"mixed-load-{lazy}"
    )
    storing = make_request(
        f"mixed-store-{lazy}", num_blocks=1, token_seed=80000
    )
    store_transfer = start_store(harness, storing, 1)
    assert reset(harness) is False
    complete_transfer(harness, load_transfer)
    assert reset(harness) is False
    complete_transfer(harness, store_transfer)
    assert reset(harness) is True
    assert observed_hit(harness, cached, "mixed-old-load")[0] == 0
    assert observed_hit(harness, storing, "mixed-old-store")[0] == 0


@pytest.mark.parametrize("lazy", [False, True], ids=["eager", "lazy"])
def test_repeated_reset_cycles_do_not_exhaust_block_pools(tmp_path, lazy):
    harness = make_harness(
        tmp_path / f"cycles-{lazy}",
        lazy=lazy,
        num_cpu_blocks=12,
        num_gpu_blocks=24,
    )
    for cycle in range(5):
        source = make_request(
            f"cycle-{lazy}-{cycle}",
            num_blocks=2,
            token_seed=100000 + cycle * 1000,
        )
        transfer = start_store(harness, source, 2)
        assert reset(harness) is False
        complete_transfer(harness, transfer)
        assert reset(harness) is True
        assert observed_hit(harness, source, f"cycle-old-{cycle}")[0] == 0
    assert_fresh_store_works(harness, 120000)
