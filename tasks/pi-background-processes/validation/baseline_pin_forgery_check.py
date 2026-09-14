#!/usr/bin/env python3
"""Curator-only: show that tests/baseline-pins.json rejects rewritten PASS_TO_PASS baselines.

Usage: baseline_pin_forgery_check.py <genuine-baseline-junit.xml>
Copies the genuine baseline out of the image first, e.g.
  docker run --rm -v $OUT:/out <image> cp /opt/pi-baseline/coding-agent-junit.xml /out/baseline.xml
Forgeries: every passing case marked failed; the first 200 cases of each suite
dropped; every key-gated skip removed; two unlisted cases marked failed (stays
under the failure cap, so only the allowed-failure pin can reject it).
The genuine baseline must be accepted and every forgery rejected.
"""
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE.parent / "tests/check_pass_to_pass.py"
PINS = HERE.parent / "tests/baseline-pins.json"


def forge(genuine: Path, kind: str, out: Path) -> Path:
    tree = ET.parse(genuine)
    root = tree.getroot()
    if kind == "all-failed":
        for case in root.findall(".//testcase"):
            if case.find("skipped") is None and case.find("failure") is None:
                ET.SubElement(case, "failure", {"message": "forged"})
    elif kind == "drop-cases":
        for suite in root.findall(".//testsuite"):
            for case in list(suite.findall("testcase"))[:200]:
                suite.remove(case)
    elif kind == "unskip":
        for case in root.findall(".//testcase"):
            skipped = case.find("skipped")
            if skipped is not None:
                case.remove(skipped)
    elif kind == "exempt-two":
        marked = 0
        for case in root.findall(".//testcase"):
            if case.find("skipped") is None and case.find("failure") is None and "session-manager" in case.get("classname", ""):
                ET.SubElement(case, "failure", {"message": "forged exemption"})
                marked += 1
                if marked == 2:
                    break
    path = out / f"{kind}.xml"
    tree.write(path)
    return path


def verdict(baseline: Path, genuine: Path) -> dict:
    result = subprocess.run([sys.executable, str(CHECKER), str(baseline), str(genuine), str(PINS)], capture_output=True, text=True)
    summary = json.loads(result.stdout.strip().splitlines()[-1])
    return {"exit_code": result.returncode, "passed": summary["passed"], "pin_problems": summary.get("baseline_pin_problems", [])}


def main() -> int:
    genuine = Path(sys.argv[1])
    report = {}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        report["genuine"] = verdict(genuine, genuine)
        for kind in ["all-failed", "drop-cases", "unskip", "exempt-two"]:
            report[kind] = verdict(forge(genuine, kind, out), genuine)
    ok = report["genuine"]["passed"] and all(not v["passed"] for k, v in report.items() if k != "genuine")
    print(json.dumps({"ok": ok, "report": report}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
