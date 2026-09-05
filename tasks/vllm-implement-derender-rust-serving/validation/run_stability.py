#!/usr/bin/env python3
"""Repeat the complete verifier with fresh server processes in each round."""
import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--container", required=True)
p.add_argument("--logs", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument("--expected-reward", type=int, choices=[0, 1], required=True)
p.add_argument("--rounds", type=int, default=5)
a = p.parse_args()
task = Path(__file__).resolve().parents[1]
hashes = {str(f.relative_to(task)): hashlib.sha256(f.read_bytes()).hexdigest()
          for f in sorted((task / "tests").rglob("*")) if f.is_file() and "__pycache__" not in f.parts}
a.output.mkdir(parents=True, exist_ok=True)
records = []
baseline_names = None
for number in range(1, a.rounds + 1):
    destination = a.output / f"round-{number}"
    destination.mkdir(exist_ok=True)
    with (destination / "stdout.log").open("w") as log:
        subprocess.run(["docker", "exec", a.container, "bash", "/tests/test.sh"],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    for f in a.logs.iterdir():
        if f.is_file(): shutil.copy2(f, destination / f.name)
    reward = json.loads((destination / "reward.json").read_text())
    root = ET.parse(destination / "derender.xml").getroot()
    suites = list(root.iter("testsuite"))
    counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ["tests", "failures", "errors", "skipped"]}
    failed_names = sorted(c.get("name") for c in root.iter("testcase") if c.find("failure") is not None)
    if baseline_names is None: baseline_names = failed_names
    record = {"round": number, **reward, **counts, "failed_cases": failed_names}
    records.append(record)
    print(json.dumps(record), flush=True)
    (a.output / "results.json").write_text(json.dumps({"test_hashes": hashes, "rounds": records}, indent=2) + "\n")
    assert reward["compile_exit_code"] == reward["regression_exit_code"] == 0, record
    assert reward["reward"] == a.expected_reward, record
    assert counts["tests"] == 67 and counts["errors"] == counts["skipped"] == 0, record
    assert failed_names == baseline_names, record
    assert hashes == {str(f.relative_to(task)): hashlib.sha256(f.read_bytes()).hexdigest()
                      for f in sorted((task / "tests").rglob("*")) if f.is_file() and "__pycache__" not in f.parts}
