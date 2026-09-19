#!/usr/bin/env python3
"""Challenge a candidate with independently derived contract cases (curator-only).

Runs inside the pinned task image after the candidate patch is applied, with the
task's validation/ directory mounted at /validation and an output directory at
/logs/verifier. It executes validation/independent_probe.mjs (a real pi
AgentSession with the faux provider, loading the candidate extension from
dist/) and records the result.

Cases (none copied from the verifier suites): relative cwd resolution with a
Unicode error pattern and non-ASCII output; intermittent output keeping a bash
command in the foreground; paging past the end of a log; bg_kill on a process
that already finished.

    docker run --rm --init -v $TASK/validation:/validation:ro -v $OUT:/logs/verifier \\
      -e PI_OFFLINE=1 -e PI_TELEMETRY=0 -e PI_NO_LOCAL_LLM=1 -e HOME=/tmp/vh \\
      <image-with-candidate-applied> python3 /validation/independent_challenge.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

WORKDIR = Path(os.environ.get("PI_WORKSPACE", "/workspace/pi")) / "packages/coding-agent"
PROBE = Path(__file__).with_name("independent_probe.mjs")
OUTPUT = Path(os.environ.get("INDEPENDENT_OUTPUT", "/logs/verifier"))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result_file = OUTPUT / "independent-result.json"
    # Copy the probe next to the package so workspace imports resolve like the verifier's.
    target = WORKDIR / "test" / "__independent__"
    target.mkdir(parents=True, exist_ok=True)
    probe = target / PROBE.name
    shutil.copy2(PROBE, probe)
    env = dict(os.environ, PI_OFFLINE="1", PI_TELEMETRY="0", PI_NO_LOCAL_LLM="1")
    for key in list(env):
        if key.endswith(("_API_KEY", "_AUTH_TOKEN", "_OAUTH_TOKEN")):
            env.pop(key)
    with (OUTPUT / "independent.log").open("w") as log:
        proc = subprocess.run(
            ["node", str(probe), str(result_file)],
            cwd=WORKDIR,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
    summary = {"exit_code": proc.returncode, "passed": False, "checks": {}}
    if result_file.is_file():
        data = json.loads(result_file.read_text())
        summary["passed"] = bool(data.get("passed"))
        summary["checks"] = data.get("checks", {})
    (OUTPUT / "independent-summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False))
    shutil.rmtree(target, ignore_errors=True)
    return 0 if summary["passed"] and proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
