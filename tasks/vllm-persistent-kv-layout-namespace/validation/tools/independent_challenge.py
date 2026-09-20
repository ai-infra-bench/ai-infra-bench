#!/usr/bin/env python3
"""Curator-only namespace challenge with an unseen model and topology."""

from __future__ import annotations

from pathlib import Path
import tempfile

import torch

from verifier_support import (
    LayoutCase,
    RunnerCase,
    layout_specific_parallel_miss,
    portable_cross_parallel_lifecycle,
    runner_transition_lifecycle,
    same_runner_restart_lifecycle,
)


def main() -> int:
    runner_case = RunnerCase(
        name="independent-fp32",
        model_name="org/independent-layout-model",
        dtype=torch.float32,
    )
    layout_case = LayoutCase(
        name="independent-three-layer",
        model_name="org/independent-layout-model",
        groups=((16, ("layer0", "layer1", "layer2")),),
    )
    with tempfile.TemporaryDirectory(prefix="persistent-namespace-independent-") as temp:
        root = Path(temp)
        runner_transition_lifecycle(
            str(root / "v1-v2"), runner_case, "v1", "v2"
        )
        runner_transition_lifecycle(
            str(root / "v2-v1"), runner_case, "v2", "v1"
        )
        same_runner_restart_lifecycle(
            str(root / "v1-restart"), runner_case, "v1"
        )
        same_runner_restart_lifecycle(
            str(root / "v2-restart"), runner_case, "v2"
        )
        portable_cross_parallel_lifecycle(
            str(root / "portable"),
            layout_case,
            {"tp_size": 3, "rank": 2},
        )
        layout_specific_parallel_miss(
            str(root / "specific"),
            layout_case,
            {"pp_size": 3, "rank": 2},
        )
    print(
        {
            "passed": True,
            "model": runner_case.model_name,
            "dtype": "float32",
            "runner_directions": 2,
            "same_runner_restarts": 2,
            "portable_tp_size": 3,
            "layout_specific_pp_size": 3,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
