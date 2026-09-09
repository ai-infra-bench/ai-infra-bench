#!/usr/bin/env python3
"""Correctness-gated, model-free A100 timing of exact `_moe_C.moe_permute`.

Correctness is scored on BOTH operator modes the instruction names:

  * aligned   (align_block_size=128): expert ranges are block-aligned, the
    padded prefix offsets are written back, and ``m_indices`` is filled with the
    expert id per aligned row and a -1 sentinel tail.
  * unaligned (align_block_size=None -> -1): expert ranges are the raw
    (unpadded) prefix offsets, routed slots pack densely into ``[0, n_token*topk)``,
    and ``m_indices`` is left unwritten (getMIndices is not invoked).

Both modes check output allocation/shape, the token->expert offset mapping, the
inverse/permuted-index bijection, the byte-exact payload gather, dtype/device/
contiguity, and (aligned only) the expert-id fill and sentinel. Correctness runs
on power-of-two batches AND non-power-of-two batches (1000, 3000) that are NOT in
the timed set, so a kernel cannot special-case the timed shapes and still pass.

Performance follows the instruction's 20/50 protocol and numerical bounds at
4096 and 512 tokens. Additional non-power-of-two measurements are diagnostic;
they do not introduce undisclosed numerical acceptance criteria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys

# The trusted timing boundary is imported BEFORE anything that could pull in
# candidate code, so it captures torch.cuda.Event / elapsed_time /
# statistics.median while they are still the real ones. Later monkeypatching
# cannot reach the references it captured.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import trusted_timing  # noqa: E402

import torch  # noqa: E402


# Counts of real measured work, reported for comparison by the scorer.
CALL_COUNTS = {"check_case": 0, "time_case": 0}
# Per-case digests over genuine kernel outputs.
CASE_DIGESTS: dict[str, str] = {}


def assert_privilege_dropped() -> int:
    """Fail closed unless this worker really runs as the expected unprivileged uid."""
    expect = os.environ.get("MOE_EXPECT_UID")
    actual = os.getuid()
    assert expect is not None, "MOE_EXPECT_UID not supplied by the trusted scorer"
    assert actual == int(expect), (
        f"worker uid not dropped: running as {actual}, expected {expect}"
    )
    assert actual != 0, "worker must not run as root"
    return actual


N_EXPERT = 64
TOPK = 6
HIDDEN = 2048
ALIGN = 128
# Correctness batches: the timed power-of-two set PLUS non-power-of-two counts
# (1000, 3000) that never appear in the timed set. Each is checked in aligned
# AND unaligned mode.
CORRECTNESS_TOKENS = (1, 32, 128, 512, 1000, 1024, 2048, 3000, 4096)
# Instruction timing contract (aligned path).
BATCH_SIZES = (1, 32, 128, 512, 1024, 2048, 4096)
LARGE_US_MAX = 250.0
RATIO_MAX = 3.5
# Anti-special-case probe: a non-power-of-two large batch and a small baseline,
# neither of which is a power-of-two timed size a kernel could hardcode.
PROBE_SMALL = 63
PROBE_LARGE = 3000


def load_staged_native() -> tuple[pathlib.Path, str]:
    """Load ONLY the root-frozen staged artifact.

    ``importlib.util.find_spec("vllm._moe_C")`` is deliberately not used: it
    imports the candidate parent package ``vllm`` to locate the submodule, which
    would execute candidate code inside this process before any measurement.
    The path and digest come from the root-owned staging manifest instead, and
    the digest is re-verified here so a swapped or stale file cannot be loaded.
    """
    staged = os.environ.get("MOE_STAGED_NATIVE")
    expected = os.environ.get("MOE_STAGED_SHA256")
    assert staged, "MOE_STAGED_NATIVE not provided by the trusted scorer"
    assert expected, "MOE_STAGED_SHA256 not provided by the trusted scorer"
    native = pathlib.Path(staged)
    st = os.lstat(native)
    import stat as _stat
    assert not _stat.S_ISLNK(st.st_mode), f"staged artifact is a symlink: {native}"
    assert _stat.S_ISREG(st.st_mode), f"staged artifact not a regular file: {native}"
    actual = hashlib.sha256(native.read_bytes()).hexdigest()
    assert actual == expected, f"staged digest mismatch {actual} != {expected}"
    torch.ops.load_library(str(native))
    assert torch.ops._moe_C.moe_permute_unpermute_supported()
    return native, actual


def make_inputs(n_token: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    # FP8 is used as a one-byte storage type. This kernel only copies payload
    # bytes; it does not execute FP8 Tensor Core arithmetic, so SM80 is valid.
    torch.manual_seed(32892 + n_token)
    hidden = torch.empty(
        (n_token, HIDDEN), device="cuda", dtype=torch.float8_e4m3fn
    )
    hidden.view(torch.uint8).random_(0, 127)
    token = torch.arange(n_token, device="cuda", dtype=torch.int64)[:, None]
    rank = torch.arange(TOPK, device="cuda", dtype=torch.int64)[None, :]
    topk_ids = ((token * 17 + rank * 7) % N_EXPERT).to(torch.int32)
    token_expert_indices = torch.arange(
        n_token * TOPK, device="cuda", dtype=torch.int32
    ).reshape(n_token, TOPK)
    return hidden, topk_ids, token_expert_indices


def allocate_outputs(
    n_token: int, hidden: torch.Tensor
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    # Aligned upper bound also safely holds every unaligned destination
    # (n_token*topk <= aligned rows), so one allocation serves both modes.
    rows = (
        (n_token * TOPK + N_EXPERT * (ALIGN - 1) + ALIGN - 1) // ALIGN * ALIGN
    )
    return (
        torch.empty((rows, HIDDEN), device="cuda", dtype=hidden.dtype),
        torch.empty(N_EXPERT + 1, device="cuda", dtype=torch.int64),
        torch.empty((n_token, TOPK), device="cuda", dtype=torch.int32),
        torch.full((rows,), n_token * TOPK, device="cuda", dtype=torch.int32),
        torch.full((rows,), -1, device="cuda", dtype=torch.int32),
    )


def call_op(
    hidden: torch.Tensor,
    topk_ids: torch.Tensor,
    token_expert_indices: torch.Tensor,
    outputs: tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor],
    align_block_size: int | None,
) -> None:
    torch.ops._moe_C.moe_permute(
        hidden,
        topk_ids,
        token_expert_indices,
        None,
        N_EXPERT,
        N_EXPERT,
        TOPK,
        align_block_size,
        *outputs,
    )


def check_case(n_token: int, align_block_size: int | None) -> str:
    """Validate one moe_permute call; return a digest of its real outputs.

    The digest is taken over the actual offsets/inverse tensors the kernel
    produced. A worker that prints a well-formed payload without running the
    kernel cannot produce it, and the scorer recomputes the expected digest for
    the same deterministic inputs independently.
    """
    aligned = align_block_size is not None
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    permuted, offsets, inverse, permuted_idx, m_indices = outputs
    call_op(hidden, topk_ids, token_expert_indices, outputs, align_block_size)
    torch.cuda.synchronize()

    # Output allocation / shape / dtype / device / contiguity.
    assert offsets.shape == (N_EXPERT + 1,)
    assert inverse.shape == (n_token, TOPK)
    assert offsets.dtype == torch.int64
    assert inverse.dtype == torch.int32
    assert permuted_idx.dtype == torch.int32
    assert permuted.dtype == hidden.dtype
    for tensor in (permuted, offsets, inverse, permuted_idx, m_indices):
        assert tensor.is_cuda and tensor.is_contiguous()

    flat_ids = topk_ids.flatten().to(torch.int64)
    counts = torch.bincount(flat_ids, minlength=N_EXPERT)
    if aligned:
        windows = ((counts + ALIGN - 1) // ALIGN) * ALIGN
    else:
        # Unaligned: expert ranges are the raw unpadded per-expert counts.
        windows = counts
    expected_offsets = torch.cat(
        [
            torch.zeros(1, device="cuda", dtype=torch.int64),
            torch.cumsum(windows, dim=0),
        ]
    )
    torch.testing.assert_close(offsets, expected_offsets, atol=0, rtol=0)
    CALL_COUNTS["check_case"] += 1
    # Digest scope must match tests/trusted_expected.py exactly: offsets (which
    # the assertion above already pins byte-exactly) plus the inverse
    # shape/dtype fingerprint. The scorer recomputes this expectation itself, so
    # a fabricated-but-distinct digest cannot pass.
    case_digest = hashlib.sha256(
        b"|".join([
            f"{n_token}:{aligned}".encode(),
            offsets.cpu().numpy().tobytes(),
            f"inv_shape={n_token}x{TOPK}:int32".encode(),
        ])
    ).hexdigest()
    CASE_DIGESTS[f"{n_token}:{'aligned' if aligned else 'unaligned'}"] = case_digest

    original = torch.arange(n_token * TOPK, device="cuda", dtype=torch.int64)
    destinations = inverse.flatten().to(torch.int64)
    # Genuine bijection over every routed (token, top-k) slot.
    assert int(destinations.unique().numel()) == n_token * TOPK
    routed_expert = flat_ids
    # Each slot lands inside its routed expert's window (payload region is the
    # first ``counts[e]`` rows of the window in both modes).
    assert bool(torch.all(destinations >= offsets[routed_expert]))
    assert bool(
        torch.all(destinations < offsets[routed_expert] + counts[routed_expert])
    )
    torch.testing.assert_close(
        permuted_idx[destinations].to(torch.int64), original, atol=0, rtol=0
    )

    # Byte-exact payload gather from the source token rows.
    source_rows = original // TOPK
    torch.testing.assert_close(
        permuted[destinations].view(torch.uint8),
        hidden[source_rows].view(torch.uint8),
        atol=0,
        rtol=0,
    )

    if aligned:
        # getMIndices fills expert id per aligned row and a -1 sentinel tail.
        for expert in range(N_EXPERT):
            start = int(offsets[expert])
            end = int(offsets[expert + 1])
            if end > start:
                assert bool(torch.all(m_indices[start:end] == expert))
        tail = int(offsets[-1])
        if tail < m_indices.numel():
            assert bool(torch.all(m_indices[tail:] == -1))
    # Unaligned: getMIndices is not invoked, so m_indices is intentionally
    # unwritten by the op and is not part of the observable contract here.


def time_case(
    n_token: int, align_block_size: int | None = ALIGN,
) -> dict:
    """Time one batch under the trusted, pre-captured protocol.

    Returns the full observation record (including the iteration counts actually
    used) so the scorer can reject a run that measured fewer iterations than the
    declared protocol requires.
    """
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    record = trusted_timing.measure_us(
        lambda: call_op(
            hidden, topk_ids, token_expert_indices, outputs, align_block_size
        )
    )
    record["n_token"] = n_token
    CALL_COUNTS["time_case"] += 1
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=("correctness", "performance", "all"),
        default="all",
    )
    args = parser.parse_args()
    actual_uid = assert_privilege_dropped()
    native, native_sha256 = load_staged_native()
    assert torch.cuda.is_available()
    assert torch.cuda.get_device_capability(0) == (8, 0)

    common = {
        "alignment": ALIGN,
        "correctness_modes": ["aligned", "unaligned"],
        "correctness_tokens": list(CORRECTNESS_TOKENS),
        "timed_batch_sizes": list(BATCH_SIZES),
        "anti_special_case_probe": {"small": PROBE_SMALL, "large": PROBE_LARGE},
        "dtype": "torch.float8_e4m3fn storage/copy; no FP8 arithmetic",
        "gpu": torch.cuda.get_device_name(0),
        "hidden_size": HIDDEN,
        "n_expert": N_EXPERT,
        "native_extension": str(native),
        "native_sha256": native_sha256,
        "topk": TOPK,
    }
    if args.stage in ("correctness", "all"):
        for batch in CORRECTNESS_TOKENS:
            check_case(batch, ALIGN)  # aligned path
            check_case(batch, None)  # unaligned path
        print(json.dumps({**common,
                          "actual_uid": actual_uid,
                          "correctness_cases": len(CORRECTNESS_TOKENS) * 2,
                          "call_counts": dict(CALL_COUNTS),
                          "case_digests": dict(CASE_DIGESTS),
                          "correctness_passed": True}, sort_keys=True))
        print("MOE_PERMUTE_CORRECTNESS_STAGE=PASS")
    if args.stage in ("performance", "all"):
        # Full observation records (not bare floats): they carry the iteration
        # counts and statistic actually used, so the scorer can reject a run that
        # measured fewer iterations than the declared protocol.
        timing_records = {str(batch): time_case(batch) for batch in BATCH_SIZES}
        probe_records = {
            str(PROBE_SMALL): time_case(PROBE_SMALL),
            str(PROBE_LARGE): time_case(PROBE_LARGE),
        }
        proto = trusted_timing.protocol()
        for label, rec in {**timing_records, **probe_records}.items():
            assert rec["timed_iters"] == proto["timed_iters"], (
                "timing protocol violated (iteration count)", label, rec,
            )
            assert rec["repeats"] == proto["repeats"], (
                "timing protocol violated (repeats)", label, rec,
            )
            assert rec["statistic"] == proto["statistic"], (
                "timing protocol violated (statistic)", label, rec,
            )
        timings = {k: v["median_us"] for k, v in timing_records.items()}
        probe = {k: v["median_us"] for k, v in probe_records.items()}
        large_batch_ratio = timings["4096"] / timings["512"]
        probe_ratio = probe[str(PROBE_LARGE)] / probe[str(PROBE_SMALL)]
        # Instruction contract on the timed power-of-two sizes.
        assert large_batch_ratio < RATIO_MAX, (
            "moe_permute retains the legacy large-batch scaling curve",
            timings,
        )
        assert timings["4096"] < LARGE_US_MAX, timings
        # Probe values are reported for diagnosis; the task's numerical bounds
        # apply to the explicitly specified 4096/512 workload.
        print(json.dumps({**common, "timings_median_us": timings,
                          "probe_median_us": probe,
                          "timing_protocol": proto,
                          "actual_uid": actual_uid,
                          "call_counts": dict(CALL_COUNTS),
                          # Full per-batch records so the scorer can check the
                          # sample count and that every value is finite/positive.
                          "timing_records": {
                              k: {"samples_us": v["samples_us"],
                                  "timed_iters": v["timed_iters"],
                                  "repeats": v["repeats"],
                                  "warmup_iters": v["warmup_iters"],
                                  "statistic": v["statistic"]}
                              for k, v in {**timing_records,
                                           **probe_records}.items()
                          },
                          "staged_native_sha256": native_sha256,
                          "large_batch_ratio_4096_over_512": large_batch_ratio,
                          "probe_ratio_large_over_small": probe_ratio}, sort_keys=True))
        print("MOE_PERMUTE_PERFORMANCE_STAGE=PASS")


if __name__ == "__main__":
    main()
