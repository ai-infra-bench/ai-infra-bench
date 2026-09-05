#!/usr/bin/env python3
"""Run declared validation variants in fresh CPU containers and retain evidence."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[1]
    config = tomllib.loads((task / "task.toml").read_text())
    manifest = json.loads((task / "validation/ci-cases.json").read_text())
    cases = [("base", None, 0), ("oracle", "solution/oracle.patch", 1)]
    cases += [(c["name"], "validation/" + c["patch"], c["expected_reward"]) for c in manifest["cases"]]
    if args.case:
        assert set(args.case) <= {c[0] for c in cases}
        cases = [case for case in cases if case[0] in args.case]
    hashes = {str(f.relative_to(task)): hashlib.sha256(f.read_bytes()).hexdigest()
              for f in sorted((task / "tests").glob("*")) if f.is_file()}
    args.output.mkdir(parents=True, exist_ok=True)

    def execute(item):
        name, patch, expected, round_number = item
        directory = args.output / f"{name}-round-{round_number}"
        directory.mkdir(exist_ok=True)
        script = "set -e\n"
        if patch:
            script += f"git apply --check /task/{patch}\ngit apply /task/{patch}\n"
        script += "bash /tests/test.sh\n"
        command = ["docker", "run", "--rm", "--network=none", "--cpus=8", "--memory=48g",
                   "--user=root", "--workdir=/workspace/vllm", "-e", "PYTHONDONTWRITEBYTECODE=1",
                   "-v", f"{task}:/task:ro", "-v", f"{task / 'tests'}:/tests:ro",
                   "-v", f"{directory}:/logs/verifier", "--entrypoint=bash",
                   config["metadata"]["image_digest"], "-c", script]
        start = time.monotonic()
        with (directory / "run.log").open("w") as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=920)
        result = {"name": name, "round": round_number, "expected_reward": expected,
                  "docker_rc": process.returncode, "seconds": round(time.monotonic() - start, 2)}
        if (directory / "reward.json").exists():
            result.update(json.loads((directory / "reward.json").read_text()))
        if (directory / "junit.xml").exists():
            root = ET.parse(directory / "junit.xml").getroot()
            suites = list(root.iter("testsuite"))
            for key in ["tests", "failures", "errors", "skipped"]:
                result[key] = sum(int(s.get(key, 0)) for s in suites)
            result["failed_cases"] = sorted(c.get("name") for c in root.iter("testcase") if c.find("failure") is not None)
        (directory / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        return result

    work = [(name, patch, expected, n) for name, patch, expected in cases for n in range(1, args.rounds + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(execute, work))
    assert hashes == {str(f.relative_to(task)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in sorted((task / "tests").glob("*")) if f.is_file()}, "tests changed during execution"
    (args.output / "results.json").write_text(json.dumps({"test_hashes": hashes, "results": results}, indent=2) + "\n")
    assert all(r.get("reward") == r["expected_reward"] and r["docker_rc"] == 0
               and r.get("errors") == r.get("skipped") == 0 for r in results), "unexpected validation outcome"


if __name__ == "__main__":
    main()
