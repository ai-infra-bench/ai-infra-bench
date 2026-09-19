#!/usr/bin/env python3
"""Challenge a candidate with independently derived contract cases (curator-only).

Runs inside the pinned task image after the candidate patch is applied, with the task's
tests/ at /tests and validation/ at /validation, output under /logs/verifier. It copies the
verifier harness (tests/at_support.ts, never a scored case) and validation/at.independent.test.ts
into packages/coding-agent/test/__verifier__/ and runs vitest on that file only.

    docker run --rm --network none -v $TASK/tests:/tests:ro -v $TASK/validation:/validation:ro \
      -v $OUT:/logs/verifier -e PI_OFFLINE=1 -e PI_TELEMETRY=0 -e PI_NO_LOCAL_LLM=1 -e HOME=/tmp/vh \
      <image-with-candidate-applied> python3 /validation/independent_challenge.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

WS = Path(os.environ.get("PI_WORKSPACE", "/workspace/pi")) / "packages/coding-agent"
OUT = Path("/logs/verifier")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    target = WS / "test/__verifier__"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    shutil.copy("/tests/at_support.ts", target / "at_support.ts")
    shutil.copy("/validation/at.independent.test.ts", target / "at.independent.test.ts")
    env = dict(os.environ, PI_WORKSPACE=str(WS.parent.parent), PI_VERIFIER_FIXTURES="/tests/fixtures", NODE_OPTIONS="--expose-gc")
    junit = OUT / "independent-junit.xml"
    proc = subprocess.run(
        ["node", "../../node_modules/vitest/vitest.mjs", "run", "--reporter=junit", f"--outputFile={junit}", "test/__verifier__/at.independent.test.ts"],
        cwd=WS, env=env, capture_output=True, text=True, timeout=600,
    )
    (OUT / "independent.log").write_text(proc.stdout + proc.stderr)
    cases = []
    if junit.exists():
        for tc in ET.parse(junit).getroot().iter("testcase"):
            failure = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
            cases.append({"name": tc.get("name"), "ok": failure is None, "message": (failure.get("message") or (failure.text or "")[:400]) if failure is not None else None})
    result = {"exit_code": proc.returncode, "passed": proc.returncode == 0 and len(cases) == 2 and all(c["ok"] for c in cases), "cases": cases}
    (OUT / "independent-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result)[:1500])
    shutil.rmtree(target, ignore_errors=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
