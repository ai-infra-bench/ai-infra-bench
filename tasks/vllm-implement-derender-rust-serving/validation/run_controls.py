#!/usr/bin/env python3
"""Qualify Base-relative controls in a retained, compiled Oracle container."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def new_derender_files(patch):
    files = {}
    current = None
    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            path = line.rstrip().split(" b/", 1)[1]
            current = path if "/routes/derender/" in path else None
            if current:
                files[current] = []
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current].append(line[1:])
    return {path: "".join(lines) for path, lines in files.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="derender-oracle-dev")
    parser.add_argument("--base-container", default="derender-base-dev")
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    task = Path(__file__).resolve().parents[1]
    cases = json.loads((task / "validation/ci-cases.json").read_text())["cases"]
    args.output.mkdir(parents=True, exist_ok=True)
    # Preserve the passing reference run before reusing the log mount.
    before = args.output / "oracle-before-controls"
    before.mkdir(exist_ok=True)
    for path in args.logs.iterdir():
        if path.is_file():
            shutil.copy2(path, before / path.name)
    records = []
    for case in cases:
        if args.case and case["name"] not in args.case:
            continue
        directory = args.output / case["name"]
        directory.mkdir(exist_ok=True)
        patch_path = task / "validation" / case["patch"]
        assert hashlib.sha256(patch_path.read_bytes()).hexdigest() == case["patch_sha256"]
        run("docker", "cp", str(patch_path), f"{args.base_container}:/tmp/control.patch")
        run("docker", "exec", args.base_container, "git", "apply", "--check", "/tmp/control.patch")
        files = new_derender_files(patch_path.read_text())
        assert len(files) == 4, files.keys()
        for relative, content in files.items():
            path = directory / Path(relative).name
            path.write_text(content)
            run("docker", "cp", str(path), f"{args.container}:/workspace/vllm/{relative}")
        with (directory / "stdout.log").open("w") as log:
            run("docker", "exec", args.container, "bash", "/tests/test.sh", stdout=log, stderr=subprocess.STDOUT)
        for path in args.logs.iterdir():
            if path.is_file():
                shutil.copy2(path, directory / path.name)
        reward = json.loads((directory / "reward.json").read_text())
        record = {"case": case["name"], "expected_reward": case["expected_reward"], **reward}
        if (directory / "derender.xml").is_file():
            root = ET.parse(directory / "derender.xml").getroot()
            suites = list(root.iter("testsuite"))
            for key in ["tests", "failures", "errors", "skipped"]:
                record[key] = sum(int(s.get(key, 0)) for s in suites)
            record["failed_cases"] = [c.get("name") for c in root.iter("testcase") if c.find("failure") is not None]
        print(json.dumps(record), flush=True)
        records.append(record)
        (args.output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
        assert reward["compile_exit_code"] == 0, record
        assert reward["regression_exit_code"] == 0, record
        assert record["errors"] == record["skipped"] == 0, record
        assert reward["reward"] == case["expected_reward"], record


if __name__ == "__main__":
    main()
