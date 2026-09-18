#!/usr/bin/env python3
"""Run the filesystem lifecycle in a child and attest full completion."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


PREFIX = "PERSISTENT_NAMESPACE_RESULT "
EXPECTED = {
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
}


def main() -> int:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    payload = None
    process = subprocess.Popen(
        [sys.executable, "/tests/test_real_filesystem_namespace.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=120)
        child_output = stdout + stderr
        markers = [
            line for line in stdout.splitlines() if line.startswith(PREFIX)
        ]
        if process.returncode != 0:
            errors.append(f"child exit code {process.returncode}")
        if len(markers) != 1:
            errors.append(f"expected one completion record, found {len(markers)}")
        else:
            try:
                payload = ast.literal_eval(markers[0][len(PREFIX) :])
            except (SyntaxError, ValueError) as exc:
                errors.append(f"invalid completion record: {type(exc).__name__}")
            if payload != EXPECTED:
                errors.append("completion record does not match required lifecycle")
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        child_output = stdout + stderr
        errors.append("filesystem lifecycle process group did not complete")

    (output / "real_filesystem_namespace.child.log").write_text(child_output)
    summary = {"passed": not errors, "errors": errors, "result": payload}
    (output / "real_filesystem_namespace.summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(child_output, end="")
    print(json.dumps(summary))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
