#!/usr/bin/env python3
"""Local replica of .github/scripts/run_task_validation.sh (no GHCR cache, no x64 hardware-check).

Runs Base, Oracle, and every validation/ci-cases.json control for one task through
the same task_ci.py + Harbor entrypoint that CI uses, and reports reward matches.

Usage:
    python3.12 tools/local_task_validation.py <task-name> <image> [case ...]

Requirements and local pitfalls:
- Python >= 3.11 (task_ci.py uses tomllib); Harbor is fetched with `uvx --from harbor==<ver>`.
- Harbor's no-network mode builds an egress sidecar with `docker buildx`; the CLI
  plugin must be installed (~/.docker/cli-plugins/docker-buildx).
- colima shares only $HOME with containers, so job and case directories default to
  ~/ai-infra-scratch/. Override with AI_INFRA_SCRATCH.
- AI_INFRA_MATRIX_JOBS=N runs N cases at once (about 3 GB per case; keep N small and do not
  overlap a matrix with a real-agent rollout).
- Each case is a full Harbor trial (image start, agent, verifier); expect roughly a
  minute per case for CPU tasks.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path(os.environ.get("AI_INFRA_SCRATCH", Path.home() / "ai-infra-scratch"))
HARBOR_VERSION = os.environ.get("HARBOR_VERSION", "0.22.0")
CI = REPO / ".github/scripts/task_ci.py"
PY = sys.executable
HARBOR = ["uvx", "--from", f"harbor=={HARBOR_VERSION}", "harbor"]
TASK = ""
JOBS = Path()


def ci(*args: str) -> str:
    return subprocess.run(
        [PY, str(CI), *args], cwd=REPO, check=True, text=True, capture_output=True
    ).stdout.strip()


def main() -> int:
    global TASK, JOBS
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    TASK = sys.argv[1]
    image = sys.argv[2]
    wanted = sys.argv[3:]
    JOBS = SCRATCH / "harbor-jobs" / TASK
    (SCRATCH / "cases").mkdir(parents=True, exist_ok=True)
    JOBS.mkdir(parents=True, exist_ok=True)
    print(ci("validate", TASK))
    print(ci("image-check", "--task", TASK, "--image", image))
    cases = json.loads(ci("cases", "--task", TASK))
    expected = {c["name"]: c["expected_reward"] for c in cases}
    names = wanted or [c["name"] for c in cases]
    parallel = max(1, int(os.environ.get("AI_INFRA_MATRIX_JOBS", "1")))

    def run_case(name: str) -> tuple[str, int, bool, int]:
        case_dir = Path(tempfile.mkdtemp(prefix="ai-infra-case.", dir=str(SCRATCH / "cases")))
        agent = ci(
            "prepare-case",
            "--task",
            TASK,
            "--image",
            image,
            "--case",
            name,
            "--output",
            str(case_dir),
        )
        job = f"{TASK}--{name}"
        shutil.rmtree(JOBS / job, ignore_errors=True)
        print(f"=============== {job} agent={agent} expected={expected[name]}", flush=True)
        start = time.time()
        with open(JOBS / f"{job}.harbor.log", "w") as log:
            run = subprocess.run(
                [
                    *HARBOR,
                    "run",
                    "--path",
                    str(case_dir),
                    "--agent",
                    agent,
                    "--env",
                    "docker",
                    "--jobs-dir",
                    str(JOBS),
                    "--job-name",
                    job,
                    "--n-concurrent",
                    "1",
                    "--cpus",
                    "ignore",
                    "--memory",
                    "ignore",
                    "--delete",
                    "--yes",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        elapsed = int(time.time() - start)
        check = subprocess.run(
            [
                PY,
                str(CI),
                "check-result",
                "--result",
                str(JOBS / job / "result.json"),
                "--expected-reward",
                str(expected[name]),
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        ok = check.returncode == 0
        print(
            f"RESULT {name}: {'OK' if ok else 'MISMATCH'} expected={expected[name]} "
            f"harbor_exit={run.returncode} elapsed={elapsed}s\n"
            f"{check.stdout.strip()[-400:]}{check.stderr.strip()[-400:]}",
            flush=True,
        )
        shutil.rmtree(case_dir, ignore_errors=True)
        return (name, expected[name], ok, elapsed)

    # AI_INFRA_MATRIX_JOBS=N runs N cases at once (each is its own Harbor job and container);
    # the verifier's PASS_TO_PASS suite needs a few GB per case, so keep N small and never
    # overlap a matrix with a real-agent rollout.
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        outcomes = list(pool.map(run_case, names))
    print("SUMMARY")
    for name, exp, ok, elapsed in outcomes:
        print(f"  {name:48s} expected={exp} {'OK' if ok else 'MISMATCH'} {elapsed}s")
    return 0 if all(o[2] for o in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
