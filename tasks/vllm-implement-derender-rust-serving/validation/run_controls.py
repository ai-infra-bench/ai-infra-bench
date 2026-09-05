#!/usr/bin/env python3
"""Run complete Base-relative variants in a dedicated compilation container.

The container must mount this task at /task, its tests at /tests, and --output
at /qualification. Only this disposable container's source checkout is reset;
Cargo build artifacts are reused, with changed source freshly materialized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[1]
    manifest = json.loads((task / "validation/ci-cases.json").read_text())
    cases = [{"name": "base", "patch": None, "expected_reward": 0},
             {"name": "oracle", "patch": "solution/oracle.patch", "expected_reward": 1}]
    cases += [{**c, "patch": "validation/" + c["patch"]} for c in manifest["cases"]]
    if args.case:
        assert set(args.case) <= {c["name"] for c in cases}
        cases = [c for c in cases if c["name"] in args.case]
    hashes = {str(p.relative_to(task)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (task / "tests").glob("*") if p.is_file()}
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for case in cases:
        directory = args.output / case["name"]
        directory.mkdir(exist_ok=False)
        patch = case["patch"]
        patch_hash = hashlib.sha256((task / patch).read_bytes()).hexdigest() if patch else None
        if "patch_sha256" in case:
            assert patch_hash == case["patch_sha256"]
        script = "set -e\npython /task/validation/materialize_variant.py"
        script += f" /task/{patch}\n" if patch else "\n"
        script += f"mkdir -p /logs\nrm -f /logs/verifier\nln -s /qualification/{case['name']} /logs/verifier\nbash /tests/test.sh\n"
        with (directory / "stdout.log").open("w") as log:
            subprocess.run(["docker", "exec", args.container, "bash", "-c", script],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=3600)
        reward = json.loads((directory / "reward.json").read_text())
        root = ET.parse(directory / "derender.xml").getroot()
        suites = list(root.iter("testsuite"))
        record = {"case": case["name"], "patch_sha256": patch_hash,
                  "expected_reward": case["expected_reward"], **reward}
        record.update({k: sum(int(s.get(k, 0)) for s in suites)
                       for k in ["tests", "failures", "errors", "skipped"]})
        record["failed_cases"] = [c.get("name") for c in root.iter("testcase")
                                  if any(c.find(tag) is not None for tag in ("failure", "error"))]
        records.append(record)
        print(json.dumps(record), flush=True)
        (args.output / "results.json").write_text(json.dumps({"test_hashes": hashes, "cases": records}, indent=2) + "\n")
        assert reward["compile_exit_code"] == reward["regression_exit_code"] == 0, record
        assert record["tests"] == 67 and record["skipped"] == 0, record
        assert reward["reward"] == case["expected_reward"], record
        if case["expected_reward"]:
            assert record["errors"] == record["failures"] == 0, record
        assert all(hashlib.sha256((task / p).read_bytes()).hexdigest() == h for p, h in hashes.items())


if __name__ == "__main__":
    main()
