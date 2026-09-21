#!/usr/bin/env python3
"""Run local Harbor author checks against a retained image; never publish anything."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--harbor", default="harbor")
    args = parser.parse_args()
    task = Path(__file__).resolve().parent.parent
    repo = task.parents[1]
    helper = repo / ".github/scripts/task_ci.py"
    cases = [{"name": "base", "expected_reward": 0}, {"name": "oracle", "expected_reward": 1}]
    cases.extend(json.loads((task / "validation/ci-cases.json").read_text())["cases"])
    if args.cases:
        unknown = set(args.cases) - {case["name"] for case in cases}
        if unknown:
            parser.error(f"unknown cases: {sorted(unknown)}")
        cases = [case for case in cases if case["name"] in args.cases]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, str(helper), "validate", task.name], cwd=repo, check=True)
    subprocess.run([sys.executable, str(helper), "image-check", "--task", task.name, "--image", args.image], cwd=repo, check=True)

    def run_case(case: dict) -> dict:
        started = time.monotonic()
        name = case["name"]
        prepared = output / "prepared" / name
        prepared.parent.mkdir(exist_ok=True)
        agent = subprocess.check_output([
            sys.executable, str(helper), "prepare-case", "--task", task.name,
            "--image", args.image, "--case", name, "--output", str(prepared),
        ], cwd=repo, text=True).strip()
        job_name = f"pi-plan-mode--{name}"
        command = [args.harbor, "run", "--path", str(prepared), "--agent", agent,
                   "--env", "docker", "--jobs-dir", str(output / "jobs"),
                   "--job-name", job_name, "--n-concurrent", "1", "--delete", "--yes"]
        with (output / f"{name}.log").open("w") as stream:
            completed = subprocess.run(command, cwd=repo, stdout=stream, stderr=subprocess.STDOUT)
        result = output / "jobs" / job_name / "result.json"
        check = subprocess.run([
            sys.executable, str(helper), "check-result", "--result", str(result),
            "--expected-reward", str(case["expected_reward"]),
        ], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        record = {"case": name, "expected_reward": case["expected_reward"],
                  "harbor_exit_code": completed.returncode, "check_exit_code": check.returncode,
                  "check_output": check.stdout.strip(), "result": str(result), "command": command,
                  "elapsed_sec": round(time.monotonic() - started, 2)}
        (output / f"{name}.check.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record), flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_case, cases))
    summary = {"recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "image": args.image, "harbor": subprocess.check_output([args.harbor, "--version"], text=True).strip(),
               "results": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if all(r["harbor_exit_code"] == 0 and r["check_exit_code"] == 0 for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
