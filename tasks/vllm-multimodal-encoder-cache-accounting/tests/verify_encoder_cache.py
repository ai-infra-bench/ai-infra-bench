#!/usr/bin/env python3
"""Behavioral verifier for prompt-space/embedding-space cache migration.

TRUSTED PARENT/WORKER BOUNDARY:
This verifier runs as root. It spawns the candidate validation as a non-root
worker (uid 65534) via subprocess, captures the worker's structured output over
a pipe, and writes reward.txt itself. The worker never touches /logs/verifier.
"""

from __future__ import annotations

import json
import subprocess
import sys
import traceback


# The parent requires exactly these stages in the worker payload. Missing,
# extra, malformed, or duplicated stages are all treated as failures.
REQUIRED_STAGES = {
    "placeholder_coordinates",
    "partial_mapping",
    "cache_lifecycle",
    "multiple_items",
    "scheduler_partial_budget",
    "model_runner_compact_gather",
    "registry_capacity",
    "scheduled_cache_lifecycle",
}


WORKER_CODE = r'''
import json
import sys
import traceback
from types import SimpleNamespace

import torch

from vllm.multimodal.inputs import MultiModalFeatureSpec, PlaceholderRange
import vllm.multimodal.registry as registry_module
from vllm.multimodal.registry import MultiModalRegistry
from vllm.multimodal.profiling import MultiModalProfiler
from vllm.v1.core.encoder_cache_manager import EncoderCacheManager
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.request import Request
import vllm.v1.worker.gpu_model_runner as runner_module
from vllm.v1.worker.gpu_model_runner import GPUModelRunner


class SparseRequest(Request):
    """Minimal production Request shape using the candidate's own count API."""

    def __init__(self, request_id: str, masks: list[torch.Tensor | None], dense_length=5):
        self.request_id = request_id
        self.mm_features = []
        for index, mask in enumerate(masks):
            length = dense_length if mask is None else len(mask)
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


def sparse_mask(length: int, indices: list[int]) -> torch.Tensor:
    mask = torch.zeros(length, dtype=torch.bool)
    if indices:
        mask[torch.tensor(indices)] = True
    return mask


def check_placeholder_coordinates():
    """Embedding-row capacity accounting, observed through EncoderCacheManager.

    No internal PlaceholderRange accessor is named or asserted here. Each case
    declares a prompt-space span plus an is_embed mask, and the expected number
    of embedding rows is read back out of the production allocator's own free-slot
    accounting. A prompt-space implementation charges `length` rows and fails the
    exact-fit / one-short pair below.
    """
    cases = [
        # (prompt_length, embed_indices or None for dense, expected_embedding_rows)
        (0, [], 0),
        (0, None, 0),
        (5, None, 5),
        (5, [0, 1, 2, 3, 4], 5),
        (5, [], 0),
        (5, [1, 3, 4], 3),
        (100, [5, 15, 25, 35, 45, 55, 65, 75], 8),
        (64, [0, 63], 2),
    ]
    observed = []
    for length, indices, expected_rows in cases:
        mask = None if indices is None else sparse_mask(length, indices)

        # Exact-fit cache: allocation must consume precisely expected_rows.
        request = SparseRequest(f"cap-{length}-{expected_rows}", [mask], dense_length=length)
        manager = EncoderCacheManager(cache_size=expected_rows)
        if not manager.can_allocate(request, 0, expected_rows, 0):
            raise AssertionError(
                f"length={length} rows={expected_rows}: can_allocate False on exact-fit cache"
            )
        manager.allocate(request, 0)
        if manager.num_free_slots != 0:
            raise AssertionError(
                f"length={length} rows={expected_rows}: exact-fit cache left "
                f"{manager.num_free_slots} free slots, expected 0"
            )
        observed.append(expected_rows - manager.num_free_slots)

        # One row short: a correct embedding-space accounting must refuse.
        if expected_rows > 0:
            tight = SparseRequest(f"tight-{length}-{expected_rows}", [mask], dense_length=length)
            short = EncoderCacheManager(cache_size=expected_rows - 1)
            if short.can_allocate(tight, 0, expected_rows, 0):
                raise AssertionError(
                    f"length={length}: can_allocate True with cache_size="
                    f"{expected_rows - 1} for {expected_rows} embedding rows"
                )
    return {"cases": len(cases), "embedding_rows": observed}


def encode_into_cache(runner, features, outputs):
    """Supply model outputs, then execute the candidate's real cache writer.

    Media batching and model inference only produce the embedding tensors here.
    The production encoder loop, cache representation, and later gather remain
    candidate code; tests never inject a presumed cache layout.
    """
    runner.device = torch.device("cpu")
    runner.pin_memory = False
    runner._batch_mm_kwargs_from_scheduler = lambda output: (
        [SimpleNamespace(modality=feature.modality) for feature in features],
        [(feature.identifier, feature.mm_position) for feature in features],
    )
    runner.model = SimpleNamespace(
        embed_multimodal=lambda **kwargs: [output.clone() for output in outputs]
    )
    runner.maybe_save_ec_to_connector = lambda *args: None
    original = runner_module.group_mm_kwargs_by_modality
    runner_module.group_mm_kwargs_by_modality = lambda *args, **kwargs: [
        (features[0].modality, len(features), {})
    ]
    try:
        GPUModelRunner._execute_mm_encoder(runner, SimpleNamespace())
    finally:
        runner_module.group_mm_kwargs_by_modality = original


def check_partial_mapping():
    """Partial prompt-window mapping through the real encoder cache and gather.

    The prompt->embedding coordinate translation is verified only by what the
    production gather path actually returns for a partially computed request, so
    no internal range accessor is referenced by name.
    """
    length = 5
    mask = sparse_mask(length, [1, 3, 4])
    compact = torch.arange(length * 4, dtype=torch.float32).reshape(length, 4)[:3]

    # Every nonempty scheduled prompt window, including windows with no embedding rows.
    # Production scheduling omits requests with zero scheduled tokens.
    selected = [False, True, False, True, True]
    cases = [
        (start, end - start,
         (sum(selected[:start]), sum(selected[:end])), selected[start:end])
        for start in range(length) for end in range(start + 1, length + 1)
    ]
    results = []
    for computed, scheduled, (lo, hi), expected_mask in cases:
        position = PlaceholderRange(0, length, mask)
        feature = MultiModalFeatureSpec(
            data=None, modality="image", identifier="pm", mm_position=position
        )

        class BoolBuffer:
            def __init__(self, size):
                self.cpu = torch.empty(size, dtype=torch.bool)

            def copy_to_gpu(self, count):
                return self.cpu[:count].clone()

        runner = object.__new__(GPUModelRunner)
        runner.input_batch = SimpleNamespace(req_ids=["req"])
        runner.requests = {
            "req": SimpleNamespace(num_computed_tokens=computed, mm_features=[feature])
        }
        runner.encoder_cache = {}
        runner.is_mm_embed = BoolBuffer(max(scheduled, 1))
        runner.is_multimodal_pruning_enabled = False
        runner.uses_mrope = False
        encode_into_cache(runner, [feature], [compact])
        scheduler_output = SimpleNamespace(
            total_num_scheduled_tokens=scheduled,
            num_scheduled_tokens={"req": scheduled},
        )
        gathered, out_mask = GPUModelRunner._gather_mm_embeddings(
            runner, scheduler_output
        )
        if hi > lo:
            if len(gathered) != 1:
                raise AssertionError(
                    f"computed={computed} scheduled={scheduled}: gathered "
                    f"{len(gathered)} tensors, expected 1"
                )
            torch.testing.assert_close(gathered[0], compact[lo:hi])
        elif sum(t.shape[0] for t in gathered) != 0:
            raise AssertionError("empty embedding interval returned nonempty rows")
        if out_mask.tolist() != expected_mask:
            raise AssertionError(
                f"computed={computed} scheduled={scheduled}: mask="
                f"{out_mask.tolist()}, expected {expected_mask}"
            )
        results.append({"prompt_window": [computed, computed + scheduled],
                        "compact_rows": [lo, hi]})
    return {"cases": len(cases), "windows": results}


def check_cache_lifecycle():
    first = SparseRequest("first", [sparse_mask(100, [5, 15, 25, 35, 45, 55, 65, 75])])
    manager = EncoderCacheManager(cache_size=8)
    if not manager.can_allocate(first, 0, 8, 0):
        raise AssertionError("can_allocate returned False for first request")
    manager.allocate(first, 0)
    if manager.num_free_slots != 0:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 0")
    if first.mm_features[0].identifier not in manager.cached:
        raise AssertionError("identifier not in manager.cached")

    manager.free_encoder_input(first, 0)
    second = SparseRequest("second", [sparse_mask(20, [2, 7, 12, 17])])
    if not manager.can_allocate(second, 0, 4, 0):
        raise AssertionError("can_allocate returned False for second request")
    if first.mm_features[0].identifier not in manager.freed:
        raise AssertionError("first identifier not in manager.freed")
    manager.allocate(second, 0)
    if manager.num_free_slots != 4:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 4")
    if second.mm_features[0].identifier not in manager.cached:
        raise AssertionError("second identifier not in manager.cached")
    return {"eviction": True, "free_slots": manager.num_free_slots}


def check_multiple_items_and_zero_embeddings():
    request = SparseRequest(
        "multi",
        [sparse_mask(10, [1, 4, 7, 9]), None, torch.zeros(6, dtype=torch.bool)],
    )
    manager = EncoderCacheManager(cache_size=9)
    if not manager.can_allocate(request, 0, 4, 0):
        raise AssertionError("can_allocate failed for item 0")
    manager.allocate(request, 0)
    if not manager.can_allocate(request, 1, 5, 0):
        raise AssertionError("can_allocate failed for item 1")
    manager.allocate(request, 1)
    if manager.num_free_slots != 0:
        raise AssertionError(f"num_free_slots={manager.num_free_slots}, expected 0 after items 0,1")
    slots_before_zero = manager.num_free_slots
    if not manager.can_allocate(request, 2, 0, 0):
        raise AssertionError("can_allocate failed for zero-embedding item 2")
    manager.allocate(request, 2)
    if manager.num_free_slots != slots_before_zero:
        raise AssertionError("zero-embedding item changed num_free_slots")
    return {"items": 3, "allocated_embedding_rows": 9, "zero_item": True}


def check_scheduler_partial_budget():
    # The real allocator determines admission; internal call counts are free.
    request = SparseRequest("scheduler", [sparse_mask(100, [5, 15, 25, 35])])
    scheduler = object.__new__(Scheduler)
    scheduler.ec_connector = None
    scheduler.is_encoder_decoder = False
    scheduler.scheduler_config = SimpleNamespace(disable_chunked_mm_input=False)

    for capacity, compute_budget in ((4, 4), (3, 4), (4, 3)):
        scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=capacity)
        scheduled, num_new, budget, external = Scheduler._try_schedule_encoder_inputs(
            scheduler, request, num_computed_tokens=15, num_new_tokens=7,
            encoder_compute_budget=compute_budget,
        )
        expected = ([0], 7, 0, []) if capacity == compute_budget == 4 else ([], 0, compute_budget, [])
        actual = (scheduled, num_new, budget, external)
        if actual != expected:
            raise AssertionError(f"capacity={capacity} budget={compute_budget}: {actual} != {expected}")
        if scheduled:
            scheduler.encoder_cache_manager.allocate(request, 0)
            if scheduler.encoder_cache_manager.num_free_slots != 0:
                raise AssertionError("scheduled item did not consume its four embedding rows")

    # A fresh real cache keeps this case independent of the earlier allocation.
    scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=4)
    scheduled, _, budget, _ = Scheduler._try_schedule_encoder_inputs(
        scheduler, request, num_computed_tokens=16, num_new_tokens=6,
        encoder_compute_budget=4,
    )
    if scheduled != [] or budget != 4:
        raise AssertionError(f"no-embedding-overlap returned scheduled={scheduled}, budget={budget}")
    return {"partial_embedding_overlap": True, "budget_units": "embedding_rows"}


def check_model_runner_compact_gather():
    """Round-trip ordered sparse, dense, and all-false items in one request.

    The historical stage name refers to encoder output rows, not a required
    cache representation. Every scheduled nonempty window observes real output.
    """
    positions = [
        PlaceholderRange(2, 5, sparse_mask(5, [1, 3, 4])),
        PlaceholderRange(9, 3, None),
        PlaceholderRange(13, 2, sparse_mask(2, [])),
    ]
    features = [MultiModalFeatureSpec(
        data=None, modality="image", identifier=f"roundtrip-{i}", mm_position=p
    ) for i, p in enumerate(positions)]
    outputs = [torch.arange(12, dtype=torch.float32).reshape(3, 4) + 100,
               torch.arange(12, dtype=torch.float32).reshape(3, 4) + 200,
               torch.empty((0, 4), dtype=torch.float32)]

    class BoolBuffer:
        def __init__(self):
            self.cpu = torch.empty(16, dtype=torch.bool)

        def copy_to_gpu(self, count):
            return self.cpu[:count].clone()

    runner = object.__new__(GPUModelRunner)
    runner.input_batch = SimpleNamespace(req_ids=["req"])
    runner.requests = {
        "req": SimpleNamespace(num_computed_tokens=0, mm_features=features)
    }
    runner.encoder_cache = {}
    runner.is_mm_embed = BoolBuffer()
    runner.is_multimodal_pruning_enabled = False
    runner.uses_mrope = False
    encode_into_cache(runner, features, outputs)
    expected_mask = torch.zeros(16, dtype=torch.bool)
    expected_payload = torch.zeros((16, 4))
    for position, output in zip(positions, outputs):
        selected = (torch.ones(position.length, dtype=torch.bool)
                    if position.is_embed is None else position.is_embed)
        expected_mask[position.offset:position.offset + position.length] = selected
        indices = torch.arange(position.offset, position.offset + position.length)[selected]
        expected_payload[indices] = output
    windows = 0
    for start in range(16):
        for end in range(start + 1, 17):
            runner.requests["req"].num_computed_tokens = start
            scheduler_output = SimpleNamespace(
                total_num_scheduled_tokens=end - start,
                num_scheduled_tokens={"req": end - start},
            )
            gathered, mask = GPUModelRunner._gather_mm_embeddings(runner, scheduler_output)
            actual = torch.cat(gathered, dim=0) if gathered else outputs[2]
            torch.testing.assert_close(mask, expected_mask[start:end])
            torch.testing.assert_close(actual,
                expected_payload[start:end][expected_mask[start:end]])
            windows += 1
    return {"items": 3, "windows": windows, "encoder_rows": [3, 3, 0]}


def check_scheduled_cache_lifecycle():
    """Follow actual scheduling decisions from a cold request to cached reads."""
    from vllm.sampling_params import SamplingParams
    from vllm.v1.worker.gpu_input_batch import CachedRequestState

    specs = [(3, 8, [2, 5]), (11, 3, []), (14, 3, None),
             (17, 6, [1, 4]), (23, 0, [])]
    features, outputs, selected = [], [], []
    for i, (offset, length, indices) in enumerate(specs):
        mask = None if indices is None else sparse_mask(length, indices)
        local = list(range(length)) if indices is None else indices
        rows = torch.arange(len(local) * 4, dtype=torch.float32).reshape(-1, 4) + i * 100
        outputs.append(rows)
        selected.append([offset + j for j in local])
        features.append(MultiModalFeatureSpec(
            data=SimpleNamespace(modality="image", rows=rows), modality="image",
            identifier=f"chain-{i}", mm_position=PlaceholderRange(offset, length, mask)))
    params = SamplingParams(max_tokens=1)
    request = Request(request_id="chain", prompt_token_ids=[1] * 24,
                      sampling_params=params, pooling_params=None,
                      eos_token_id=None, mm_features=features)
    state = CachedRequestState(req_id="chain", prompt_token_ids=[1] * 24,
                               mm_features=features, sampling_params=params,
                               generator=None, block_ids=([],),
                               num_computed_tokens=0, output_token_ids=[])
    scheduler = object.__new__(Scheduler)
    scheduler.ec_connector = None
    scheduler.is_encoder_decoder = False
    scheduler.scheduler_config = SimpleNamespace(disable_chunked_mm_input=False)
    manager = scheduler.encoder_cache_manager = EncoderCacheManager(cache_size=7)

    class BoolBuffer:
        def __init__(self):
            self.cpu = torch.empty(24, dtype=torch.bool)

        def copy_to_gpu(self, count):
            return self.cpu[:count].clone()

    runner = object.__new__(GPUModelRunner)
    runner.input_batch = SimpleNamespace(req_ids=["chain"])
    runner.requests = {"chain": state}
    runner.encoder_cache = {}
    runner.is_mm_embed = BoolBuffer()
    runner.device = torch.device("cpu")
    runner.pin_memory = False
    runner.is_multimodal_pruning_enabled = False
    runner.uses_mrope = False
    runner.maybe_save_ec_to_connector = lambda *args: None
    runner.model = SimpleNamespace(embed_multimodal=lambda rows: [r.clone() for r in rows])
    # Substitute media grouping/model output only. The real candidate batching
    # method selects items from the real scheduler output, including zero items.
    original = runner_module.group_mm_kwargs_by_modality
    runner_module.group_mm_kwargs_by_modality = lambda items, **kwargs: [
        ("image", len(items), {"rows": [item.rows for item in items]})]
    cuts = [0, 5, 6, 8, 9, 14, 15, 17, 18, 19, 21, 22, 24]
    encoded = set()
    charges, total_selected = [], 0
    try:
        for start, end in zip(cuts, cuts[1:]):
            ids, count, remaining, external = Scheduler._try_schedule_encoder_inputs(
                scheduler, request, start, end - start, 7)
            needed = [i for i, positions in enumerate(selected)
                      if i not in encoded and any(start <= p < end for p in positions)]
            charge = sum(len(outputs[i]) for i in needed)
            if (ids, count, remaining, external) != (needed, end - start, 7 - charge, []):
                raise AssertionError(f"window={[start,end]} schedule={(ids,count,remaining,external)}")
            for i in ids:
                manager.allocate(request, i)
            output = SimpleNamespace(
                scheduled_encoder_inputs={"chain": ids} if ids else {},
                total_num_scheduled_tokens=count, num_scheduled_tokens={"chain": count})
            GPUModelRunner._execute_mm_encoder(runner, output)
            gathered, mask = GPUModelRunner._gather_mm_embeddings(runner, output)
            expected_rows = [rows[j] for positions, rows in zip(selected, outputs)
                             for j, p in enumerate(positions) if start <= p < end]
            expected = torch.stack(expected_rows) if expected_rows else torch.empty((0, 4))
            actual = torch.cat(gathered) if gathered else torch.empty((0, 4))
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            wanted_mask = [any(p in positions for positions in selected) for p in range(start, end)]
            if mask.tolist() != wanted_mask:
                raise AssertionError(f"window={[start,end]} mask={mask.tolist()} != {wanted_mask}")
            encoded.update(ids)
            if manager.num_free_slots != 7 - sum(len(outputs[i]) for i in encoded):
                raise AssertionError("cache allocation differs from full encoded item rows")
            charges.append(7 - remaining)
            total_selected += actual.shape[0]
            request.num_computed_tokens = state.num_computed_tokens = end
    finally:
        runner_module.group_mm_kwargs_by_modality = original
    return {"windows": len(charges), "items": len(features),
            "encoded_rows": 7 - manager.num_free_slots,
            "selected_rows": total_selected, "charges": charges}


def check_registry_profiles_embedding_capacity():
    """Observe actual encoder compute/cache capacity, not a registry default."""
    cases = [(100, [5, 15, 25, 35, 45, 55, 65, 75]),
             (41, [2, 11, 29, 38]), (9, None), (12, []), (0, []), (0, None)]
    measured = []
    for length, indices in cases:
        mask = None if indices is None else sparse_mask(length, indices)
        position = PlaceholderRange(0, length, mask)
        measured.append(observe_encoder_capacity(position))
    return {"cases": measured}


def main() -> None:
    stages = {
        "placeholder_coordinates": check_placeholder_coordinates,
        "partial_mapping": check_partial_mapping,
        "cache_lifecycle": check_cache_lifecycle,
        "multiple_items": check_multiple_items_and_zero_embeddings,
        "scheduler_partial_budget": check_scheduler_partial_budget,
        "model_runner_compact_gather": check_model_runner_compact_gather,
        "registry_capacity": check_registry_profiles_embedding_capacity,
        "scheduled_cache_lifecycle": check_scheduled_cache_lifecycle,
    }
    passed = {}
    failures = {}
    for name, check in stages.items():
        try:
            passed[name] = check()
        except Exception as exc:
            failures[name] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
    fresh = None
    try:
        fresh = observe_fresh(json.load(sys.stdin))
    except Exception as exc:
        failures["fresh_observations"] = {"message": str(exc), "traceback": traceback.format_exc()}
    result = {
        "observations": fresh,
        "coordinate_spaces": ["prompt", "embedding"],
        "failures": failures,
        "stages": passed,
    }
    # Delimit the payload: importing vllm emits Triton/CUDA log lines on stdout,
    # so the parent must not assume stdout is pure JSON.
    print("---WORKER-PAYLOAD-BEGIN---")
    print(json.dumps(result, indent=2, sort_keys=True))
    print("---WORKER-PAYLOAD-END---")
    if failures:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
'''


from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from encoder_contract import workload, expected
WORKER_CODE = WORKER_CODE.replace("def main() -> None:",
    Path(__file__).with_name("encoder_capacity_worker.py").read_text() + "\n" +
    Path(__file__).with_name("encoder_fresh_worker.py").read_text() + "\n\ndef main() -> None:", 1)


PAYLOAD_BEGIN = "---WORKER-PAYLOAD-BEGIN---"
PAYLOAD_END = "---WORKER-PAYLOAD-END---"


def extract_payload(stdout: str) -> tuple[str, str | None]:
    """Pull the delimited JSON payload out of the worker's stdout.

    Importing vllm writes Triton/CUDA notices to stdout, so the payload is
    framed. Exactly one complete frame must be present: zero frames means the
    worker never reached its reporting step, and more than one means an edited
    worker emitted a partial payload before the real one.
    """
    begins = stdout.count(PAYLOAD_BEGIN)
    ends = stdout.count(PAYLOAD_END)
    if begins != 1 or ends != 1:
        return "", "worker_payload_frame_count"
    body = stdout.split(PAYLOAD_BEGIN, 1)[1].split(PAYLOAD_END, 1)[0]
    return body, None


def expected_observations():
    selected = [False, True, False, True, True]
    windows = [
        {"prompt_window": [start, end],
         "compact_rows": [sum(selected[:start]), sum(selected[:end])]}
        for start in range(5) for end in range(start + 1, 6)
    ]
    return {
        "scheduled_cache_lifecycle": {"windows": 12, "items": 5,
            "encoded_rows": 7, "selected_rows": 7,
            "charges": [0, 2, 0, 0, 0, 3, 0, 0, 2, 0, 0, 0]},
        "placeholder_coordinates": {"cases": 8,
                                    "embedding_rows": [0, 0, 5, 5, 0, 3, 8, 2]},
        "partial_mapping": {"cases": len(windows), "windows": windows},
        "cache_lifecycle": {"eviction": True, "free_slots": 4},
        "multiple_items": {"items": 3, "allocated_embedding_rows": 9,
                           "zero_item": True},
        "scheduler_partial_budget": {"partial_embedding_overlap": True,
                                     "budget_units": "embedding_rows"},
        "model_runner_compact_gather": {"items": 3, "windows": 136,
                                        "encoder_rows": [3, 3, 0]},
        "registry_capacity": {"cases": [
            {"scheduler": [max(1, n), max(1, n)], "runner": max(1, n)}
            for n in (8, 4, 9, 0, 0, 0)]},
    }


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def run_worker() -> dict:
    """Spawn the validation worker as uid 65534 (nobody), capture structured output."""
    inputs = workload()
    expected_values = expected(inputs)
    try:
        result = subprocess.run(
            ["runuser", "-u", "nobody", "--", "python3", "-I", "-c", WORKER_CODE],
            input=json.dumps(inputs),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "verdict": "FAIL",
            "reason": "worker_timeout",
            "timeout_sec": 300,
        }
    except Exception as exc:
        return {
            "verdict": "FAIL",
            "reason": "worker_spawn_failed",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    payload_text, payload_error = extract_payload(result.stdout)
    if payload_error is not None:
        return {
            "verdict": "FAIL",
            "reason": payload_error,
            "worker_exit": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:2000],
        }

    if result.returncode == 0:
        try:
            worker_output = json.loads(payload_text, object_pairs_hook=reject_duplicate_keys)
        except ValueError as exc:
            return {
                "verdict": "FAIL",
                "reason": "worker_output_invalid_json",
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
                "error": str(exc),
            }

        # Fail-closed completeness gate. A zero exit is necessary but not
        # sufficient: the parent independently re-checks the payload shape,
        # every required stage, and the worker's own failure map.
        if not isinstance(worker_output, dict):
            return {
                "verdict": "FAIL",
                "reason": "worker_output_not_object",
                "payload_type": type(worker_output).__name__,
            }

        stages = worker_output.get("stages")
        if not isinstance(stages, dict):
            return {
                "verdict": "FAIL",
                "reason": "worker_stages_malformed",
                "stages_type": type(stages).__name__,
            }

        failures = worker_output.get("failures")
        if not isinstance(failures, dict):
            return {
                "verdict": "FAIL",
                "reason": "worker_failures_malformed",
                "failures_type": type(failures).__name__,
            }
        if failures:
            return {
                "verdict": "FAIL",
                "reason": "worker_reported_failures_with_zero_exit",
                "failures": failures,
            }

        worker_stages = set(stages.keys())
        missing = REQUIRED_STAGES - worker_stages
        unexpected = worker_stages - REQUIRED_STAGES
        if missing or unexpected:
            return {
                "verdict": "FAIL",
                "reason": "incomplete_stage_coverage",
                "missing_stages": sorted(missing),
                "unexpected_stages": sorted(unexpected),
                "executed_stages": sorted(worker_stages),
            }

        # Every stage must have returned a structured (non-empty) result.
        malformed = sorted(
            name for name, value in stages.items()
            if not isinstance(value, dict) or not value
        )
        if malformed:
            return {
                "verdict": "FAIL",
                "reason": "stage_result_malformed",
                "malformed_stages": malformed,
            }

        mismatched = [name for name, expected in expected_observations().items()
                      if stages[name] != expected]
        if mismatched:
            return {"verdict": "FAIL", "reason": "behavioral_observation_mismatch",
                    "mismatched_stages": sorted(mismatched)}

        observations = worker_output.get("observations")
        if observations != expected_values:
            return {"verdict": "FAIL", "reason": "fresh_behavioral_observation_mismatch",
                    "inputs": inputs, "observed": observations, "expected": expected_values}
        return {
            "inputs": inputs,
            "observations": observations,
            "verdict": "PASS",
            "worker_exit": 0,
            "stages": stages,
        }
    else:
        try:
            worker_output = json.loads(payload_text, object_pairs_hook=reject_duplicate_keys)
            return {
                "verdict": "FAIL",
                "reason": "worker_stage_failures",
                "worker_exit": result.returncode,
                "failures": worker_output.get("failures", {}),
                "stages": worker_output.get("stages", {}),
            }
        except ValueError:
            return {
                "verdict": "FAIL",
                "reason": "worker_crash_or_invalid_output",
                "worker_exit": result.returncode,
                "stdout": result.stdout[:2000],
                "stderr": result.stderr[:2000],
            }


def main() -> None:
    import os
    if os.getuid() != 0:
        print(json.dumps({"verdict": "FAIL", "reason": "verifier_not_root", "uid": os.getuid()}))
        sys.exit(1)

    result = run_worker()
    print(json.dumps(result, indent=2, sort_keys=True))

    if result["verdict"] == "PASS":
        print("ENCODER_CACHE_VERIFIER=PASS")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
