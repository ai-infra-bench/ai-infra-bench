#!/usr/bin/env python3
"""Correctness-gated, model-free A100 timing of exact `_moe_C.moe_permute`."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import statistics

import torch


N_EXPERT = 64
TOPK = 6
HIDDEN = 2048
ALIGN = 128
BATCH_SIZES = (1, 32, 128, 512, 1024, 2048, 4096)


def load_candidate_native() -> pathlib.Path:
    spec = importlib.util.find_spec("vllm._moe_C")
    assert spec and spec.origin
    native = pathlib.Path(spec.origin).resolve()
    assert native.is_relative_to(pathlib.Path("/app"))
    torch.ops.load_library(str(native))
    assert torch.ops._moe_C.moe_permute_unpermute_supported()
    return native


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
) -> None:
    torch.ops._moe_C.moe_permute(
        hidden,
        topk_ids,
        token_expert_indices,
        None,
        N_EXPERT,
        N_EXPERT,
        TOPK,
        ALIGN,
        *outputs,
    )


def check_case(n_token: int) -> None:
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    permuted, offsets, inverse, permuted_idx, m_indices = outputs
    call_op(hidden, topk_ids, token_expert_indices, outputs)
    torch.cuda.synchronize()

    flat_ids = topk_ids.flatten().to(torch.int64)
    counts = torch.bincount(flat_ids, minlength=N_EXPERT)
    aligned_counts = ((counts + ALIGN - 1) // ALIGN) * ALIGN
    expected_offsets = torch.cat(
        [
            torch.zeros(1, device="cuda", dtype=torch.int64),
            torch.cumsum(aligned_counts, dim=0),
        ]
    )
    torch.testing.assert_close(offsets, expected_offsets, atol=0, rtol=0)

    original = torch.arange(n_token * TOPK, device="cuda", dtype=torch.int64)
    destinations = inverse.flatten().to(torch.int64)
    assert int(destinations.unique().numel()) == n_token * TOPK
    routed_expert = flat_ids
    assert bool(torch.all(destinations >= offsets[routed_expert]))
    assert bool(torch.all(destinations < offsets[routed_expert] + counts[routed_expert]))
    torch.testing.assert_close(
        permuted_idx[destinations].to(torch.int64), original, atol=0, rtol=0
    )

    source_rows = original // TOPK
    torch.testing.assert_close(
        permuted[destinations].view(torch.uint8),
        hidden[source_rows].view(torch.uint8),
        atol=0,
        rtol=0,
    )

    for expert in range(N_EXPERT):
        start = int(offsets[expert])
        end = int(offsets[expert + 1])
        if end > start:
            assert bool(torch.all(m_indices[start:end] == expert))
    tail = int(offsets[-1])
    if tail < m_indices.numel():
        assert bool(torch.all(m_indices[tail:] == -1))


def time_case(n_token: int, trials: int = 5, iterations: int = 50) -> float:
    hidden, topk_ids, token_expert_indices = make_inputs(n_token)
    outputs = allocate_outputs(n_token, hidden)
    for _ in range(20):
        call_op(hidden, topk_ids, token_expert_indices, outputs)
    torch.cuda.synchronize()

    samples = []
    for _ in range(trials):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        for _ in range(iterations):
            call_op(hidden, topk_ids, token_expert_indices, outputs)
        end.record()
        end.synchronize()
        samples.append(start.elapsed_time(end) * 1000.0 / iterations)
    return statistics.median(samples)


def main() -> None:
    native = load_candidate_native()
    assert torch.cuda.is_available()
    assert torch.cuda.get_device_capability(0) == (8, 0)

    for batch in BATCH_SIZES:
        check_case(batch)
    timings = {str(batch): round(time_case(batch), 3) for batch in BATCH_SIZES}
    print(
        json.dumps(
            {
                "alignment": ALIGN,
                "batch_sizes": list(BATCH_SIZES),
                "correctness_cases": len(BATCH_SIZES),
                "correctness_passed": True,
                "dtype": "torch.float8_e4m3fn storage/copy; no FP8 arithmetic",
                "gpu": torch.cuda.get_device_name(0),
                "hidden_size": HIDDEN,
                "n_expert": N_EXPERT,
                "native_extension": str(native),
                "timings_median_us": timings,
                "topk": TOPK,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
