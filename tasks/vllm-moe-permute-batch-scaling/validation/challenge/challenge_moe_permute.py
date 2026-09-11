#!/usr/bin/env python3
"""Independent fresh challenge for the native _moe_C.moe_permute batch scaling.

Curator-side only: not the agent verifier, not mounted into the agent image,
not referenced by instruction.md. It enters through the same production native
operator (torch.ops._moe_C.moe_permute) but on token counts and a routing
pattern derived independently of tests/verify_moe_permute.py (whose BATCH_SIZES
are 1/32/128/512/1024/2048/4096 with a fixed 17*token+7*rank routing).

Two independent invariants are re-derived here:

1. Correctness: the permutation the kernel produces must be a genuine bijection
   that groups every (token, top-k) slot under its routed expert within
   expert-aligned offset windows, and the permuted payload must be a byte-exact
   gather of the source rows.

2. Batch scaling: the task's defect is a large-batch scaling regression -- the
   Base kernel is functionally correct but its per-call latency grows
   super-linearly with the routed-slot count. The correct solution keeps the
   large-batch cost flat. Correctness alone does NOT separate Base (or a
   perf-only control) from the solution, so we also assert the scaling contract
   the production verifier scores, at the public 4096/512 sizes with this challenge's independent routing.

Phase D runs this on the built A100 native image (rebuilt from the candidate
csrc) against Oracle (PASS) and a semantically different correct alternative
(PASS). A batch-scaling-broken Base kernel and the diagnosis-only control (which
leaves the scaling curve intact) must FAIL the scaling invariant.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import statistics
import sys
import traceback

import torch


N_EXPERT = 64
TOPK = 6
HIDDEN = 2048
ALIGN = 128
# Fresh token counts, none of which appear in verify_moe_permute.BATCH_SIZES.
FRESH_TOKENS = (7, 63, 129, 257, 1000, 3000)


def load_staged_native() -> tuple[pathlib.Path, str]:
    """Load ONLY the root-frozen staged artifact, verifying its SHA-256.

    ``find_spec("vllm._moe_C")`` is deliberately avoided: locating that submodule
    imports the candidate parent package ``vllm`` first, executing candidate code
    before any observation is made. A stale or swapped ``.so`` is rejected by the
    digest comparison.
    """
    import os
    import stat as _stat
    staged = os.environ.get("MOE_STAGED_NATIVE")
    expected = os.environ.get("MOE_STAGED_SHA256")
    assert staged, "MOE_STAGED_NATIVE not provided by the trusted wrapper"
    assert expected, "MOE_STAGED_SHA256 not provided by the trusted wrapper"
    native = pathlib.Path(staged)
    st = os.lstat(native)
    assert not _stat.S_ISLNK(st.st_mode), f"staged artifact is a symlink: {native}"
    assert _stat.S_ISREG(st.st_mode), f"staged artifact not regular: {native}"
    actual = hashlib.sha256(native.read_bytes()).hexdigest()
    assert actual == expected, f"staged digest mismatch {actual} != {expected}"
    torch.ops.load_library(str(native))
    assert torch.ops._moe_C.moe_permute_unpermute_supported()
    return native, actual


def make_inputs(n_token: int):
    torch.manual_seed(70001 + n_token)
    hidden = torch.empty((n_token, HIDDEN), device="cuda", dtype=torch.float8_e4m3fn)
    hidden.view(torch.uint8).random_(0, 127)
    token = torch.arange(n_token, device="cuda", dtype=torch.int64)[:, None]
    rank = torch.arange(TOPK, device="cuda", dtype=torch.int64)[None, :]
    # Fresh routing pattern (distinct multipliers from the verifier's 17/7).
    topk_ids = ((token * 23 + rank * 11 + 3) % N_EXPERT).to(torch.int32)
    token_expert_indices = torch.arange(
        n_token * TOPK, device="cuda", dtype=torch.int32
    ).reshape(n_token, TOPK)
    return hidden, topk_ids, token_expert_indices


def allocate_outputs(n_token: int, hidden: torch.Tensor):
    rows = (n_token * TOPK + N_EXPERT * (ALIGN - 1) + ALIGN - 1) // ALIGN * ALIGN
    return (
        torch.empty((rows, HIDDEN), device="cuda", dtype=hidden.dtype),
        torch.empty(N_EXPERT + 1, device="cuda", dtype=torch.int64),
        torch.empty((n_token, TOPK), device="cuda", dtype=torch.int32),
        torch.full((rows,), n_token * TOPK, device="cuda", dtype=torch.int32),
        torch.full((rows,), -1, device="cuda", dtype=torch.int32),
    )


def call_op(hidden, topk_ids, token_expert_indices, outputs, align_block_size):
    torch.ops._moe_C.moe_permute(
        hidden, topk_ids, token_expert_indices, None,
        N_EXPERT, N_EXPERT, TOPK, align_block_size, *outputs,
    )


def check_case(n_token: int, align_block_size: int | None) -> dict:
    """Validate one moe_permute call. ``align_block_size`` None => unaligned.

    Aligned: expert ranges are block-aligned, aligned offsets are written back,
    and m_indices is filled per aligned row with a -1 sentinel tail. Unaligned:
    expert ranges are the raw unpadded prefix offsets, routed slots pack densely
    into [0, n_token*topk), and m_indices is left unwritten by the op.
    """
    aligned = align_block_size is not None
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    permuted, offsets, inverse, permuted_idx, m_indices = outputs
    call_op(hidden, topk_ids, token_expert_indices, outputs, align_block_size)
    torch.cuda.synchronize()

    flat_ids = topk_ids.flatten().to(torch.int64)
    counts = torch.bincount(flat_ids, minlength=N_EXPERT)
    windows = ((counts + ALIGN - 1) // ALIGN) * ALIGN if aligned else counts
    expected_offsets = torch.cat(
        [torch.zeros(1, device="cuda", dtype=torch.int64), torch.cumsum(windows, dim=0)]
    )
    torch.testing.assert_close(offsets, expected_offsets, atol=0, rtol=0)

    original = torch.arange(n_token * TOPK, device="cuda", dtype=torch.int64)
    destinations = inverse.flatten().to(torch.int64)
    # Genuine bijection over all routed slots.
    assert int(destinations.unique().numel()) == n_token * TOPK
    assert bool(torch.all(destinations >= offsets[flat_ids]))
    assert bool(torch.all(destinations < offsets[flat_ids] + counts[flat_ids]))
    torch.testing.assert_close(
        permuted_idx[destinations].to(torch.int64), original, atol=0, rtol=0
    )
    # Byte-exact payload gather.
    source_rows = original // TOPK
    torch.testing.assert_close(
        permuted[destinations].view(torch.uint8),
        hidden[source_rows].view(torch.uint8),
        atol=0, rtol=0,
    )
    if aligned:
        # Expert-id fill within each window and -1 sentinel tail.
        for expert in range(N_EXPERT):
            start = int(offsets[expert])
            end = int(offsets[expert + 1])
            if end > start:
                assert bool(torch.all(m_indices[start:end] == expert))
        tail = int(offsets[-1])
        if tail < m_indices.numel():
            assert bool(torch.all(m_indices[tail:] == -1))
    return {"n_token": n_token, "routed_slots": n_token * TOPK,
            "mode": "aligned" if aligned else "unaligned"}



def check_large_expert_count(align):
    global N_EXPERT, TOPK, HIDDEN
    previous = N_EXPERT, TOPK, HIDDEN
    try:
        N_EXPERT, TOPK, HIDDEN = 2049, 3, 128
        result = check_case(11, align)
        result["n_expert"] = N_EXPERT
        return result
    finally:
        N_EXPERT, TOPK, HIDDEN = previous


# Use the public performance boundary with independent payload/routing inputs.
# Fresh correctness shapes above remain independent of the main verifier.
SCALE_SMALL = 512
SCALE_LARGE = 4096
LARGE_US_MAX = 250.0
RATIO_MAX = 3.5


def time_case(n_token: int, trials: int = 5, iterations: int = 50) -> float:
    # Scaling defect lives on the aligned path; time that path.
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    for _ in range(20):
        call_op(hidden, topk_ids, token_expert_indices, outputs, ALIGN)
    torch.cuda.synchronize()
    samples = []
    for _ in range(trials):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(iterations):
            call_op(hidden, topk_ids, token_expert_indices, outputs, ALIGN)
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end) * 1000.0 / iterations)
    return statistics.median(samples)


def check_scaling() -> dict:
    small = time_case(SCALE_SMALL)
    large = time_case(SCALE_LARGE)
    ratio = large / small
    assert large < LARGE_US_MAX, (
        "large-batch latency exceeds bound (batch-scaling regression)",
        {"large_us": round(large, 2), "bound_us": LARGE_US_MAX},
    )
    assert ratio < RATIO_MAX, (
        "small->large latency growth exceeds bound (batch-scaling regression)",
        {"ratio": round(ratio, 3), "bound": RATIO_MAX,
         "small_us": round(small, 2), "large_us": round(large, 2)},
    )
    return {
        "small_token": SCALE_SMALL, "large_token": SCALE_LARGE,
        "small_us": round(small, 2), "large_us": round(large, 2),
        "ratio_large_over_small": round(ratio, 3),
    }


# Independent declaration of what MUST run: every fresh token count in BOTH
# alignment modes, plus the scaling stage. Checked by exact set equality below,
# so deleting a scenario, adding one, or emptying a body all fail.
REQUIRED_SCENARIOS = tuple(
    f"{n}:{mode}" for n in FRESH_TOKENS for mode in ("aligned", "unaligned")
) + ("experts=2049:aligned", "experts=2049:unaligned", "scaling",)


def main() -> None:
    assert torch.cuda.is_available(), "challenge requires CUDA"
    native, native_sha = load_staged_native()
    results = []
    failures = []
    observed = {}
    call_counts = {"check_case": 0, "check_scaling": 0}
    for n_token in FRESH_TOKENS:
        for align_block_size in (ALIGN, None):  # aligned AND unaligned
            mode = "aligned" if align_block_size is not None else "unaligned"
            key = f"{n_token}:{mode}"
            try:
                rec = check_case(n_token, align_block_size)
                call_counts["check_case"] += 1
                results.append(rec)
                # Positive observation, not just absence of failure.
                observed[key] = {"observed": True, "result": rec}
            except Exception as exc:  # noqa: BLE001 - report every case
                failures.append(
                    {
                        "n_token": n_token,
                        "mode": "aligned" if align_block_size is not None
                        else "unaligned",
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
    for align in (ALIGN, None):
        key = "experts=2049:" + ("aligned" if align else "unaligned")
        try:
            rec = check_large_expert_count(align)
            call_counts["check_case"] += 1
            results.append(rec)
            observed[key] = {"observed": True, "result": rec}
        except Exception as exc:
            failures.append({"stage": key, "type": type(exc).__name__,
                             "message": str(exc), "traceback": traceback.format_exc()})
    # Scaling invariant. Only measured once correctness holds -- a scaling
    # number on a kernel that produces wrong output would be meaningless.
    scaling = None
    if not failures:
        try:
            scaling = check_scaling()
            call_counts["check_scaling"] += 1
            observed["scaling"] = {"observed": True, "result": scaling}
        except Exception as exc:  # noqa: BLE001
            failures.append(
                {
                    "stage": "scaling",
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
    # Completeness gate: exact required-scenario set, real observations and the
    # expected number of measured calls. `failures == []` alone is NOT enough.
    missing = sorted(set(REQUIRED_SCENARIOS) - set(observed))
    extra = sorted(set(observed) - set(REQUIRED_SCENARIOS))
    expected_cases = len(FRESH_TOKENS) * 2 + 2
    completeness = {
        "required_scenarios": list(REQUIRED_SCENARIOS),
        "observed_scenarios": sorted(observed),
        "missing_scenarios": missing,
        "extra_scenarios": extra,
        "call_counts": call_counts,
        "expected_check_case_calls": expected_cases,
        "staged_native": str(native),
        "staged_native_sha256": native_sha,
    }
    if missing or extra:
        failures.append({"stage": "completeness",
                         "missing": missing, "extra": extra})
    if call_counts["check_case"] != expected_cases:
        failures.append({"stage": "completeness",
                         "reason": "check_case_call_count",
                         "actual": call_counts["check_case"],
                         "expected": expected_cases})
    if call_counts["check_scaling"] != 1:
        failures.append({"stage": "completeness",
                         "reason": "check_scaling_call_count",
                         "actual": call_counts["check_scaling"]})
    print(json.dumps(
        {"results": results, "scaling": scaling, "failures": failures,
         "completeness": completeness},
        indent=2, sort_keys=True,
    ))
    if failures:
        print("CHALLENGE_MOE_PERMUTE=FAIL")
        sys.exit(1)
    print(f"CHALLENGE_STAGED_SHA256={native_sha}")
    print("CHALLENGE_MOE_PERMUTE=PASS")


if __name__ == "__main__":
    main()
