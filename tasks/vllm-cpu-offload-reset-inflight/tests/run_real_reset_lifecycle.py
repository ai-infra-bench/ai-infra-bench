#!/usr/bin/env python3
"""Run candidate lifecycle code in a child and attest full completion."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


PREFIX = "CPU_OFFLOAD_LIFECYCLE_RESULT "
EXPECTED = {
    "completed": True,
    "modes": ["eager", "lazy"],
    "completion_worker_started": True,
    "entrypoint": "Scheduler.reset_prefix_cache(reset_connector=True)",
    "store_and_load_overlap": True,
    "idle_engine_liveness_checked": True,
    "transfer_owned_blocks_remained_unavailable": True,
    "old_cache_hits_after_reset": 0,
    "post_reset_store_and_hit": True,
}


def main() -> int:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    payload = None
    process = subprocess.Popen(
        [sys.executable, "/tests/test_real_reset_lifecycle.py"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=30)
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
        # Candidate code can terminate the lifecycle process while leaving its
        # completion worker alive with inherited pipes. Kill the whole session.
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        child_output = stdout + stderr
        errors.append("lifecycle process group did not complete")

    (output / "real_reset_lifecycle.child.log").write_text(child_output)
    summary = {"passed": not errors, "errors": errors, "result": payload}
    (output / "real_reset_lifecycle.summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(child_output, end="")
    print(json.dumps(summary))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
