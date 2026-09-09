#!/usr/bin/env python3
"""CUDA timing primitives captured before candidate native code loads.

The fixed 20/50 protocol follows instruction.md. Captured references avoid
simple rebinding of torch.cuda.Event or statistics.median affecting measurement.
This module still executes in the candidate worker's address space; it is not
an isolation boundary against arbitrary native code. The parent independently
validates sample completeness and recomputes the numerical acceptance criteria.
Final-entrypoint adversarial runs remain necessary.
"""

from __future__ import annotations

import statistics as _statistics

import torch as _torch

# --- Captured at import time, before candidate code is loaded. ---------------
_EVENT_CLS = _torch.cuda.Event
_SYNCHRONIZE = _torch.cuda.synchronize
_MEDIAN = _statistics.median
_ELAPSED = _EVENT_CLS.elapsed_time

# --- Fixed measurement protocol. --------------------------------------------
WARMUP_ITERS = 20
TIMED_ITERS = 50
REPEATS = 5
SEED = 32892
STATISTIC = "median"


def _fresh_events() -> tuple:
    start = _EVENT_CLS(enable_timing=True)
    end = _EVENT_CLS(enable_timing=True)
    return start, end


def measure_us(work, *, repeats: int = REPEATS,
               iterations: int = TIMED_ITERS,
               warmup: int = WARMUP_ITERS) -> dict:
    """Time ``work`` under the fixed protocol; return the observation record.

    The record carries the protocol actually used so the scorer can reject a run
    that measured fewer iterations than required.
    """
    for _ in range(warmup):
        work()
    _SYNCHRONIZE()

    samples = []
    for _ in range(repeats):
        start, end = _fresh_events()
        start.record()
        for _ in range(iterations):
            work()
        end.record()
        end.synchronize()
        # Bound method captured pre-candidate; a patched Event class on torch
        # cannot substitute this call.
        total_ms = _ELAPSED(start, end)
        samples.append(total_ms * 1000.0 / iterations)
    _SYNCHRONIZE()

    return {
        "median_us": _MEDIAN(samples),
        "samples_us": samples,
        "warmup_iters": warmup,
        "timed_iters": iterations,
        "repeats": repeats,
        "statistic": STATISTIC,
    }


def protocol() -> dict:
    """The declared protocol, for the manifest."""
    return {
        "warmup_iters": WARMUP_ITERS,
        "timed_iters": TIMED_ITERS,
        "repeats": REPEATS,
        "seed": SEED,
        "statistic": STATISTIC,
        "event_cls": f"{_EVENT_CLS.__module__}.{_EVENT_CLS.__qualname__}",
        "median_fn": f"{_MEDIAN.__module__}.{_MEDIAN.__qualname__}",
    }
