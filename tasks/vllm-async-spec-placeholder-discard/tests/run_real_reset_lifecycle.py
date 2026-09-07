#!/usr/bin/env python3
"""Run candidate code in a child and attest that its lifecycle completed."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys


PREFIX = "ASYNC_SPEC_LIFECYCLE_RESULT "
EXPECTED = {
    "completed": True,
    "entrypoint": "AsyncScheduler schedule/reset/update lifecycle",
    "concurrent_requests": 24,
    "reset_cycles": 11,
    "stale_frame_draft_widths": [5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "stale_request_frames_delivered": 264,
    "stale_placeholder_tokens_discarded": 384,
    "normal_progress_events": 24,
    "negative_placeholder_events": 0,
}


def main() -> int:
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    payload = None
    try:
        process = subprocess.run(
            [sys.executable, "/tests/test_real_reset_lifecycle.py"],
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        child_output = process.stdout + process.stderr
        markers = [
            line for line in process.stdout.splitlines() if line.startswith(PREFIX)
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
    except subprocess.TimeoutExpired as exc:
        child_output = (exc.stdout or "") + (exc.stderr or "")
        errors.append("lifecycle child timed out")

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
