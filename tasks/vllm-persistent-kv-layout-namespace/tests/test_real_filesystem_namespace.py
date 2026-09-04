#!/usr/bin/env python3
"""Exercise persistent compatibility through real asynchronous filesystem I/O."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from verifier_support import (
    DEFAULT_CASE,
    HIDDEN_RUNNER_CASE,
    PUBLIC_RUNNER_CASE,
    RUNNER_CASES,
    assert_runner_cache,
    layout_specific_parallel_miss,
    legacy_portable_read,
    portable_cross_parallel_lifecycle,
    store_runner_cache,
)


RUNNER_CASES_BY_NAME = {case.name: case for case in RUNNER_CASES}


def run_phase(args) -> int:
    case = RUNNER_CASES_BY_NAME[args.case]
    values = [int(value) for value in args.values.split(",")] if args.values else None
    if args.phase == "store":
        assert values is not None
        store_runner_cache(
            args.root,
            case,
            args.runner,
            values,
            key_seed=args.key_seed,
        )
    else:
        assert_runner_cache(
            args.root,
            case,
            args.runner,
            values if args.phase == "hit" else None,
            key_seed=args.key_seed,
        )
    return 0


def run_child(phase, root, case, runner, key_seed, values=None):
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--phase",
        phase,
        "--root",
        root,
        "--case",
        case.name,
        "--runner",
        runner,
        "--key-seed",
        str(key_seed),
    ]
    if values is not None:
        command.extend(["--values", ",".join(str(value) for value in values)])
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    subprocess.run(command, check=True, env=env, capture_output=True, text=True)


def cross_process_runner_miss(root, case, writer_runner, reader_runner, key_seed):
    values = [81, 82, 83]
    run_child("store", root, case, writer_runner, key_seed, values)
    run_child("miss", root, case, reader_runner, key_seed)


def cross_process_same_runner_hit(root, case, runner, key_seed):
    values = [91, 92, 93]
    run_child("store", root, case, runner, key_seed, values)
    run_child("hit", root, case, runner, key_seed, values)


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="persistent-layout-e2e-") as root:
            cross_process_runner_miss(
                f"{root}/public-v1-to-v2",
                PUBLIC_RUNNER_CASE,
                "v1",
                "v2",
                800,
            )
            cross_process_runner_miss(
                f"{root}/hidden-v2-to-v1",
                HIDDEN_RUNNER_CASE,
                "v2",
                "v1",
                900,
            )
            for index, runner in enumerate(("v1", "v2"), start=1):
                cross_process_same_runner_hit(
                    f"{root}/public-{runner}-restart",
                    PUBLIC_RUNNER_CASE,
                    runner,
                    1000 + index * 10,
                )
            for parallel in (
                {"tp_size": 4, "rank": 3},
                {"pp_size": 3, "rank": 2},
                {"pcp_size": 2, "rank": 1},
                {"dcp_size": 4, "rank": 3},
            ):
                portable_cross_parallel_lifecycle(root, DEFAULT_CASE, parallel)
            layout_specific_parallel_miss(
                root, DEFAULT_CASE, {"tp_size": 2, "rank": 1}
            )
            legacy_portable_read(root, DEFAULT_CASE)
        print(
            {
                "entrypoint": "FileSystemTierManager",
                "runner_config_entrypoint": "build_offloading_config",
                "cross_runner_misses": 2,
                "same_runner_restart_hits": 2,
                "independent_worker_processes": 8,
                "portable_cross_parallel_loads": 4,
                "layout_specific_parallel_misses": 1,
                "legacy_portable_loads": 1,
                "real_manager_restarts": True,
                "multi_key_data_roundtrips": True,
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            {
                "error": type(exc).__name__,
                "message": str(exc).splitlines()[0] if str(exc) else "no message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("store", "miss", "hit"))
    parser.add_argument("--root")
    parser.add_argument("--case", choices=tuple(RUNNER_CASES_BY_NAME))
    parser.add_argument("--runner", choices=("v1", "v2"))
    parser.add_argument("--key-seed", type=int)
    parser.add_argument("--values")
    args = parser.parse_args()
    if args.phase:
        required = (args.root, args.case, args.runner, args.key_seed)
        if any(value is None for value in required):
            parser.error("phase mode requires root, case, runner, and key seed")
        raise SystemExit(run_phase(args))
    raise SystemExit(main())
