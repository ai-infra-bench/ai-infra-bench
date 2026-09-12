#!/usr/bin/env python3
"""Independent fresh challenge for the encoder-cache embedding-row accounting.

This harness is curator-side only. It is NOT the agent verifier, is NOT mounted
into the agent image, and is NOT referenced by instruction.md. It enters through
the same production boundary the task defines (PlaceholderRange, the
EncoderCacheManager, and Scheduler._try_schedule_encoder_inputs) but on cases
derived independently of tests/verify_encoder_cache.py and validation/ci-cases.

Phase D runs it against Oracle and the semantically different correct alternate
(alternate-direct-mask-count.patch); both must print CHALLENGE_ENCODER_CACHE=PASS
and exit 0. Base and the incorrect partial-budget-omission control must fail it.

Embedding-count and subrange coordinates are observed only through the production
paths' actual allocation/gather behavior, without naming internal accessors.
"""
from __future__ import annotations

import atexit

import hashlib
import json
import os
import sys
from types import SimpleNamespace

import torch

from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
from vllm.v1.core.encoder_cache_manager import EncoderCacheManager
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.request import Request
import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.v1.worker.gpu_model_runner import GPUModelRunner


def mask_from(length: int, indices: list[int]) -> torch.Tensor:
    m = torch.zeros(length, dtype=torch.bool)
    if indices:
        m[torch.tensor(indices)] = True
    return m


def request_for(request_id: str, position) -> Request:
    """Wrap an exact PlaceholderRange in a production Request shape.

    The position is carried through verbatim, so a dense (is_embed=None) range
    keeps its own prompt length instead of inheriting a default.
    """
    from vllm.sampling_params import SamplingParams
    return Request(request_id=request_id,
        prompt_token_ids=[1] * max(1, position.offset + position.length),
        sampling_params=SamplingParams(max_tokens=1), pooling_params=None,
        eos_token_id=None, mm_features=[MultiModalFeatureSpec(
            data=None, modality="image", identifier=f"{request_id}-item-0",
            mm_position=position)])



def embedding_capacity(position, expected_rows: int):
    """Capacity accounting via the allocator's exact-fit and one-short pair."""
    request = request_for("cap-check", position)
    # Exact-fit: must succeed and consume all slots.
    manager = EncoderCacheManager(cache_size=expected_rows)
    if not manager.can_allocate(request, 0, expected_rows, 0):
        raise AssertionError(
            f"can_allocate False on exact-fit cache size={expected_rows}"
        )
    manager.allocate(request, 0)
    if manager.num_free_slots != 0:
        raise AssertionError(
            f"exact-fit cache left {manager.num_free_slots} free slots"
        )
    consumed = expected_rows - manager.num_free_slots
    # One-short: must refuse.
    if expected_rows > 0:
        tight = request_for("tight", position)
        short = EncoderCacheManager(cache_size=expected_rows - 1)
        if short.can_allocate(tight, 0, expected_rows, 0):
            raise AssertionError(
                f"can_allocate True with cache_size={expected_rows - 1}"
            )
    # Derived from the allocator's own slot accounting, not from the caller's
    # expectation, so the value is evidence the allocation actually happened.
    return consumed


def embedding_window(
    position,
    computed: int,
    scheduled: int,
    expected_lo: int,
    expected_hi: int,
    expected_mask: list[bool],
):
    """Subrange mapping via GPUModelRunner's actual gather output.

    `computed` and `scheduled` are placeholder-relative; the production gather
    works in absolute prompt coordinates, so the placeholder offset is added
    here. The supplied encoder output carries every embedding row of the placeholder (not
    a prefix cut to `expected_hi`), so a wrong subrange cannot accidentally
    match by running off the end of a truncated tensor.
    """
    total_rows = int(position.is_embed.sum().item())
    compact = torch.arange(total_rows * 4, dtype=torch.float32).reshape(total_rows, 4)
    feature = MultiModalFeatureSpec(
        data=None, modality="image", identifier="win", mm_position=position
    )

    class BoolBuffer:
        def __init__(self, size):
            self.cpu = torch.empty(size, dtype=torch.bool)

        def copy_to_gpu(self, count):
            return self.cpu[:count].clone()

    runner = object.__new__(GPUModelRunner)
    runner.input_batch = SimpleNamespace(req_ids=["req"])
    runner.requests = {
        "req": SimpleNamespace(
            num_computed_tokens=position.offset + computed, mm_features=[feature]
        )
    }
    runner.encoder_cache = {}
    runner.device = torch.device("cpu")
    runner.pin_memory = False
    # Only substitute media inputs/inference. The candidate writes its own cache
    # using the production encoder loop before its production gather reads it.
    runner._batch_mm_kwargs_from_scheduler = lambda output: (
        [SimpleNamespace(modality="image")], [("win", position)]
    )
    runner.model = SimpleNamespace(embed_multimodal=lambda **kwargs: [compact.clone()])
    runner.maybe_save_ec_to_connector = lambda *args: None
    runner.is_mm_embed = BoolBuffer(max(scheduled, 1))
    runner.is_multimodal_pruning_enabled = False
    runner.uses_mrope = False
    scheduler_output = SimpleNamespace(
        total_num_scheduled_tokens=scheduled,
        num_scheduled_tokens={"req": scheduled},
    )
    original = runner_module.group_mm_kwargs_by_modality
    runner_module.group_mm_kwargs_by_modality = lambda *args, **kwargs: [("image", 1, {})]
    try:
        GPUModelRunner._execute_mm_encoder(runner, scheduler_output)
    finally:
        runner_module.group_mm_kwargs_by_modality = original
    gathered, out_mask = GPUModelRunner._gather_mm_embeddings(runner, scheduler_output)
    if expected_hi > expected_lo:
        if len(gathered) != 1:
            raise AssertionError(
                f"computed={computed} scheduled={scheduled}: gathered "
                f"{len(gathered)} tensors, expected 1"
            )
        torch.testing.assert_close(gathered[0], compact[expected_lo:expected_hi])
        # Recover the slice from the gathered payload itself: row i of `compact`
        # starts at value i * 4, so the returned coordinates are read back out of
        # the production output rather than echoed from the arguments.
        actual_lo = int(gathered[0][0, 0].item()) // 4
        actual_hi = actual_lo + int(gathered[0].shape[0])
    elif sum(t.shape[0] for t in gathered) != 0:
        raise AssertionError(
            f"computed={computed} scheduled={scheduled}: gathered "
            f"{len(gathered)} tensors, expected none"
        )
    else:
        actual_lo = actual_hi = expected_lo
    if out_mask.tolist() != expected_mask:
        raise AssertionError(
            f"computed={computed} scheduled={scheduled}: mask="
            f"{out_mask.tolist()}, expected {expected_mask}"
        )
    # Digest gather output for diagnostics. A digest is not by itself proof
    # of execution; final-entrypoint adversarial controls are still required.
    payload = b"".join(
        [
            gathered[0].numpy().tobytes() if gathered else b"",
            bytes(out_mask.tolist()),
        ]
    )
    return [actual_lo, actual_hi, hashlib.sha256(payload).hexdigest()[:16]]


class SparseRequest(Request):
    """Minimal production Request shape; no prescribed count API."""

    def __init__(self, request_id: str, masks: list[torch.Tensor | None]):
        self.request_id = request_id
        self.mm_features = []
        for index, mask in enumerate(masks):
            length = 7 if mask is None else len(mask)
            self.mm_features.append(
                MultiModalFeatureSpec(
                    data=None,
                    modality="image",
                    identifier=f"{request_id}-item-{index}",
                    mm_position=PlaceholderRange(0, length, mask),
                )
            )

        from vllm.sampling_params import SamplingParams
        Request.__init__(self, request_id=request_id,
            prompt_token_ids=[1] * max(1, sum(f.mm_position.length for f in self.mm_features)),
            sampling_params=SamplingParams(max_tokens=1), pooling_params=None,
            eos_token_id=None, mm_features=self.mm_features)


def prefix_true(mask: torch.Tensor, upto: int) -> int:
    return int(mask[:upto].sum().item())


def challenge_capacity() -> dict:
    """Embedding-row capacity via allocator behavior on fresh test cases."""
    cases = [
        # (prompt_length, embedding_indices or None for dense, expected_rows)
        (0, [], 0),
        (0, None, 0),
        (9, None, 9),
        (7, [0, 1, 2, 3, 4, 5, 6], 7),
        (12, [], 0),
        (64, [0, 6, 13, 20, 27, 34, 41, 48, 55, 62, 63], 11),
        (30, [1, 7, 13, 19, 25], 5),
    ]
    # `rows` is accumulated from embedding_capacity's return value, which is only
    # reached once the allocator has confirmed the exact-fit/one-short pair. A
    # stage body that skips the work therefore cannot report the expected rows.
    rows = []
    for length, indices, expected_rows in cases:
        mask = None if indices is None else mask_from(length, indices)
        position = PlaceholderRange(0, length, mask)
        rows.append(embedding_capacity(position, expected_rows))
    return {"cases": len(cases), "rows": rows}


def challenge_windows() -> dict:
    """Partial window mapping via GPUModelRunner gather on fresh cases."""
    indices = [2, 5, 6, 11, 14]
    length = 16
    mask = mask_from(length, indices)
    position = PlaceholderRange(20, length, mask)

    # Each test: (num_computed, num_scheduled, expected_compact_slice, expected_mask)
    # num_computed/num_scheduled are placeholder-relative; the compact slice is in
    # embedding-row coordinates and the mask is one entry per scheduled token.
    tests = [
        # rel [4,12) covers mask positions 5,6,11 → compact rows 1:4
        (4, 8, (1, 4), [False, True, True, False, False, False, False, True]),
        # rel [0,6) covers mask positions 2,5 → compact rows 0:2
        (0, 6, (0, 2), [False, False, True, False, False, True]),
        # rel [6,15) covers mask positions 6,11,14 → compact rows 2:5
        (6, 9, (2, 5), [True, False, False, False, False, True, False, False, True]),
        # rel [14,16) covers mask position 14 → compact row 4:5
        (14, 2, (4, 5), [True, False]),
    ]
    # Valid scheduled windows containing no embedding positions.
    tests.extend([(0, 2, (0, 0), [False, False]),
                  (7, 3, (3, 3), [False, False, False])])
    # Each entry of `windows` comes back from embedding_window only after the
    # production gather has been run and its rows plus mask verified.
    windows = []
    for computed, scheduled, (lo, hi), expected_mask in tests:
        windows.append(
            embedding_window(position, computed, scheduled, lo, hi, expected_mask)
        )
    return {"tests": len(tests), "windows": windows}


def challenge_cache_lifecycle() -> dict:
    """Allocation and lazy eviction via allocator's own slot accounting."""
    first = SparseRequest("c-first", [mask_from(64, [0, 6, 13, 20, 27, 34, 41, 48, 55, 62, 63])])
    manager = EncoderCacheManager(cache_size=11)
    if not manager.can_allocate(first, 0, 11, 0):
        raise AssertionError("can_allocate False for first request")
    manager.allocate(first, 0)
    if manager.num_free_slots != 0:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 0")
    if first.mm_features[0].identifier not in manager.cached:
        raise AssertionError("first identifier not in manager.cached")

    manager.free_encoder_input(first, 0)
    second = SparseRequest("c-second", [mask_from(30, [3, 9, 21, 28])])
    if not manager.can_allocate(second, 0, 4, 0):
        raise AssertionError("can_allocate False for second request")
    manager.allocate(second, 0)
    if manager.num_free_slots != 7:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 7")
    if second.mm_features[0].identifier not in manager.cached:
        raise AssertionError("second identifier not in manager.cached")
    return {
        "free_slots": manager.num_free_slots,
        "cached": sorted(manager.cached),
    }


def challenge_multi_item_zero() -> dict:
    """Multi-item requests with a zero-embedding item."""
    request = SparseRequest(
        "c-multi",
        [
            mask_from(24, [1, 8, 15, 22]),
            None,
            torch.zeros(9, dtype=torch.bool),
        ],
    )
    manager = EncoderCacheManager(cache_size=11)
    if not manager.can_allocate(request, 0, 4, 0):
        raise AssertionError("can_allocate False for item 0")
    manager.allocate(request, 0)
    if not manager.can_allocate(request, 1, 7, 0):
        raise AssertionError("can_allocate False for item 1")
    manager.allocate(request, 1)
    if manager.num_free_slots != 0:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 0 after items 0,1")
    free_before_zero = manager.num_free_slots
    if not manager.can_allocate(request, 2, 0, 0):
        raise AssertionError("can_allocate False for zero-embedding item 2")
    manager.allocate(request, 2)
    if manager.num_free_slots != free_before_zero:
        raise AssertionError("zero-embedding item changed num_free_slots")
    return {
        "items": len(manager.cached),
        "rows": 11 - manager.num_free_slots,
        "free_slots": manager.num_free_slots,
    }


def challenge_scheduler_partial_budget() -> dict:
    """Scheduler partial budget accounting in embedding-space."""
    request = SparseRequest("c-sched", [mask_from(80, [4, 12, 33, 47, 61])])
    scheduler = object.__new__(Scheduler)
    scheduler.ec_connector = None
    scheduler.is_encoder_decoder = False
    scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=5)
    scheduler.scheduler_config = SimpleNamespace(disable_chunked_mm_input=False)

    scheduled, num_new, budget, external = Scheduler._try_schedule_encoder_inputs(
        scheduler,
        request,
        num_computed_tokens=0,
        num_new_tokens=80,
        encoder_compute_budget=5,
    )
    if scheduled != [0] or num_new != 80 or budget != 0 or external != []:
        raise AssertionError(f"_try_schedule_encoder_inputs returned unexpected: {(scheduled, num_new, budget, external)}")
    scheduler.encoder_cache_manager.allocate(request, 0)
    if scheduler.encoder_cache_manager.num_free_slots != 0:
        raise AssertionError("scheduled item did not consume five embedding rows")
    scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=5)
    scheduled, _, budget, _ = Scheduler._try_schedule_encoder_inputs(
        scheduler,
        request,
        num_computed_tokens=13,
        num_new_tokens=19,
        encoder_compute_budget=5,
    )
    if scheduled != [] or budget != 5:
        raise AssertionError(f"no-embedding-overlap returned scheduled={scheduled}, budget={budget}")
    return {
        "budget_units": "embedding_rows",
        "no_overlap_budget": budget,
        "no_overlap_scheduled": scheduled,
    }


def challenge_cold_to_cached():
    """Independent sequential prompt traversal, with different masks and cuts."""
    from vllm.sampling_params import SamplingParams
    from vllm.v1.worker.gpu_input_batch import CachedRequestState

    positions = [PlaceholderRange(1, 9, mask_from(9, [3, 7])),
                 PlaceholderRange(12, 2, None),
                 PlaceholderRange(14, 4, mask_from(4, [])),
                 PlaceholderRange(18, 0, mask_from(0, []))]
    payloads = [torch.tensor([[17., 31.], [43., 59.]]),
                torch.tensor([[71., 89.], [97., 101.]]),
                torch.empty((0, 2)), torch.empty((0, 2))]
    features = [MultiModalFeatureSpec(data=SimpleNamespace(modality="image", value=value),
                modality="image", identifier=f"fresh-{i}", mm_position=pos)
                for i, (pos, value) in enumerate(zip(positions, payloads))]
    params = SamplingParams(max_tokens=1)
    req = Request(request_id="fresh", prompt_token_ids=[1] * 20,
                  sampling_params=params, pooling_params=None, eos_token_id=None,
                  mm_features=features)
    state = CachedRequestState(req_id="fresh", prompt_token_ids=[1] * 20,
             mm_features=features, sampling_params=params, generator=None,
             block_ids=([],), num_computed_tokens=0, output_token_ids=[])
    sched = object.__new__(Scheduler)
    sched.is_encoder_decoder = False
    sched.ec_connector = None
    sched.scheduler_config = SimpleNamespace(disable_chunked_mm_input=False)
    sched.encoder_cache_manager = EncoderCacheManager(cache_size=4)
    runner = object.__new__(GPUModelRunner)
    runner.input_batch = SimpleNamespace(req_ids=["fresh"])
    runner.requests = {"fresh": state}
    runner.encoder_cache = {}
    runner.device = torch.device("cpu")
    runner.pin_memory = False
    runner.is_multimodal_pruning_enabled = False
    runner.uses_mrope = False
    buffer = torch.empty(20, dtype=torch.bool)
    runner.is_mm_embed = SimpleNamespace(cpu=buffer, copy_to_gpu=lambda n: buffer[:n].clone())
    runner.maybe_save_ec_to_connector = lambda *args: None
    runner.model = SimpleNamespace(embed_multimodal=lambda values: [v.clone() for v in values])
    original = runner_module.group_mm_kwargs_by_modality
    runner_module.group_mm_kwargs_by_modality = lambda items, **kwargs: [
        ("image", len(items), {"values": [item.value for item in items]})]
    # These expected values derive from the public masks, not the candidate.
    steps = [(0, 4, [], 4), (4, 5, [0], 2), (5, 8, [], 4),
             (8, 9, [], 4), (9, 13, [1], 2), (13, 14, [], 4), (14, 20, [], 4)]
    truth = {4: payloads[0][0], 8: payloads[0][1],
             12: payloads[1][0], 13: payloads[1][1]}
    emitted, charges = [], []
    try:
        for lo, hi, wanted_ids, wanted_budget in steps:
            ids, count, budget, external = Scheduler._try_schedule_encoder_inputs(
                sched, req, lo, hi - lo, 4)
            assert (ids, count, budget, external) == (wanted_ids, hi - lo, wanted_budget, []), (lo, hi, ids, count, budget)
            for i in ids:
                sched.encoder_cache_manager.allocate(req, i)
            result = SimpleNamespace(scheduled_encoder_inputs={"fresh": ids} if ids else {},
                     total_num_scheduled_tokens=count, num_scheduled_tokens={"fresh": count})
            GPUModelRunner._execute_mm_encoder(runner, result)
            chunks, mask = GPUModelRunner._gather_mm_embeddings(runner, result)
            observed = torch.cat(chunks) if chunks else torch.empty((0, 2))
            wanted = [truth[p] for p in range(lo, hi) if p in truth]
            target = torch.stack(wanted) if wanted else torch.empty((0, 2))
            torch.testing.assert_close(observed, target, rtol=0, atol=0)
            assert mask.tolist() == [p in truth for p in range(lo, hi)]
            emitted.extend(observed.tolist())
            charges.append(4 - budget)
            req.num_computed_tokens = state.num_computed_tokens = hi
    finally:
        runner_module.group_mm_kwargs_by_modality = original
    assert sched.encoder_cache_manager.num_free_slots == 0
    return {"windows": len(steps), "charges": charges, "rows": emitted}


# Stages this challenge must run in full, with the exact result each one has to
# report. Declared independently of the stage table below so that deleting,
# renaming, adding or stubbing a stage is caught rather than silently accepted.
REQUIRED_STAGE_RESULTS = {
    "cold_to_cached": {"windows": 7, "charges": [0, 2, 0, 0, 2, 0, 0],
        "rows": [[17.0, 31.0], [43.0, 59.0], [71.0, 89.0], [97.0, 101.0]]},
    "capacity": {"cases": 7, "rows": [0, 0, 9, 7, 0, 11, 5]},
    "windows": {
        "tests": 6,
        "windows": [
            [1, 4, "9a784511e50d7633"],
            [0, 2, "baf64b34145a602c"],
            [2, 5, "9449a1d27aecac16"],
            [4, 5, "b80b3e01cff53320"],
            [0, 0, "96a296d224f285c6"],
            [3, 3, "709e80c88487a241"],
        ],
    },
    "cache_lifecycle": {"free_slots": 7, "cached": ["c-second-item-0"]},
    "lookahead": {"cases": 6},
    "cold_empty_resources": {"cases": 10},
    "multi_item_zero": {"items": 3, "rows": 11, "free_slots": 0},
    "scheduler_partial_budget": {
        "budget_units": "embedding_rows",
        "no_overlap_budget": 5,
        "no_overlap_scheduled": [],
    },
}


# Fail-closed marker: the only place `cleared` is set True is after the
# completeness gate has been satisfied. An atexit hook re-checks it, so any exit
# path that skips the gate -- including a bare sys.exit(0) or an unhandled error
# -- still ends in FAIL with a non-zero status.
_GATE = {"cleared": False}


def _fail_closed_on_exit() -> None:
    if _GATE["cleared"]:
        return
    print(
        "INCOMPLETE: exited without clearing the stage-completeness gate",
        file=sys.stderr,
    )
    # This is the last verdict line written, so it overrides any earlier PASS an
    # early-exit edit may have printed. Flush explicitly: os._exit skips the
    # normal buffer flush, and the non-zero status must not cost us the message.
    print("CHALLENGE_ENCODER_CACHE=FAIL", flush=True)
    sys.stderr.flush()
    os._exit(1)


def check_stage_completeness(passed: dict) -> list[str]:
    """Reject missing, extra, malformed or stubbed stage results."""
    problems = []
    observed = set(passed)
    required = set(REQUIRED_STAGE_RESULTS)
    for name in sorted(required - observed):
        problems.append(f"missing required stage: {name}")
    for name in sorted(observed - required):
        problems.append(f"unexpected stage reported: {name}")
    for name in sorted(required & observed):
        expected = REQUIRED_STAGE_RESULTS[name]
        actual = passed[name]
        if not isinstance(actual, dict):
            problems.append(f"{name}: malformed result {actual!r}, expected a dict")
            continue
        if actual != expected:
            problems.append(f"{name}: result {actual!r}, expected {expected!r}")
    return problems



def challenge_cold_empty_resources():
    count = 0
    for length, indices in [(41, [2, 11, 29, 38]), (53, [7, 18, 22, 40, 51])]:
        req = request_for("empty-resources", PlaceholderRange(0, length, mask_from(length, indices)))
        scheduler = object.__new__(Scheduler)
        scheduler.ec_connector = None
        scheduler.is_encoder_decoder = False
        scheduler.scheduler_config = SimpleNamespace(disable_chunked_mm_input=False)
        n = len(indices)
        for capacity, budget in [(0,n), (n-1,n), (n,0), (n,n-1), (n,n)]:
            scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=capacity)
            result = Scheduler._try_schedule_encoder_inputs(scheduler, req, 0, indices[0], budget)
            assert result == ([], indices[0], budget, []), (capacity, budget, result)
            count += 1
    return {"cases": count}



def challenge_lookahead():
    scheduler=object.__new__(Scheduler)
    scheduler.ec_connector=None
    scheduler.is_encoder_decoder=False
    scheduler.scheduler_config=SimpleNamespace(disable_chunked_mm_input=False)
    cases=[(None,7,7,11,2,([0],2,0,[])),
           (None,0,7,11,2,([],1,7,[])),
           (None,7,0,11,2,([],1,0,[])),
           (None,7,6,11,2,([],1,6,[])),
           ([1,5],0,0,11,2,([],2,0,[])),
           ([0,6],2,2,13,1,([0],1,0,[]))]
    for indices,capacity,budget,start,count,wanted in cases:
        mask=None if indices is None else mask_from(7,indices)
        request=request_for('lookahead',PlaceholderRange(13,7,mask))
        scheduler.encoder_cache_manager=EncoderCacheManager(cache_size=capacity)
        actual=Scheduler._try_schedule_encoder_inputs(scheduler,request,start,count,budget,shift_computed_tokens=1)
        assert actual==wanted,(indices,capacity,budget,actual,wanted)
    return {"cases":len(cases)}


def main() -> None:
    stages = {
        "cold_to_cached": challenge_cold_to_cached,
        "cold_empty_resources": challenge_cold_empty_resources,
        "lookahead": challenge_lookahead,
        "capacity": challenge_capacity,
        "windows": challenge_windows,
        "cache_lifecycle": challenge_cache_lifecycle,
        "multi_item_zero": challenge_multi_item_zero,
        "scheduler_partial_budget": challenge_scheduler_partial_budget,
    }
    passed = {}
    failures = {}
    for name, fn in stages.items():
        try:
            passed[name] = fn()
        except Exception as exc:
            import traceback
            failures[name] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
    incomplete = check_stage_completeness(passed)
    print(
        json.dumps(
            {"passed": passed, "failures": failures, "incomplete": incomplete},
            indent=2,
            sort_keys=True,
        )
    )
    if incomplete:
        for problem in incomplete:
            print(f"INCOMPLETE: {problem}", file=sys.stderr)
        print("CHALLENGE_ENCODER_CACHE=FAIL")
        sys.exit(1)
    if failures:
        print("CHALLENGE_ENCODER_CACHE=FAIL")
        sys.exit(1)
    _GATE["cleared"] = True
    print("CHALLENGE_ENCODER_CACHE=PASS")


if __name__ == "__main__":
    atexit.register(_fail_closed_on_exit)
    main()
