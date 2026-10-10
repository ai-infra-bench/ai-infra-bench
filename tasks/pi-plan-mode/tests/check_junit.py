#!/usr/bin/env python3
"""Verifier-owned inventory and independent completeness checks; no candidate imports."""
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

def inspect(path, expected):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    cases = root.findall(".//testcase")
    names = [case.get("name", "").split(" > ")[-1] for case in cases]
    totals = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "errors", "failures", "skipped")}
    failed = [name for name, case in zip(names, cases) if any(case.find(tag) is not None for tag in ("skipped", "failure", "error"))]
    problems = []
    if not suites or totals["tests"] != len(expected) or len(cases) != len(expected): problems.append("incomplete or inflated case count")
    if len(names) != len(set(names)): problems.append("duplicate testcase names")
    if set(names) != set(expected): problems.append("case inventory mismatch")
    if failed or any(totals[k] for k in ("errors", "failures", "skipped")): problems.append("not all required cases passed")
    return {"passed": not problems, "problems": problems, "totals": totals, "failed": failed, "missing": sorted(set(expected) - set(names))}

def main():
    path = Path(sys.argv[1])
    suite = sys.argv[2] if len(sys.argv) > 2 else ("lifecycle" if "lifecycle" in path.name else "contract")
    inventory = json.loads((Path(__file__).parent / "case-inventory.json").read_text())[suite]
    try: result = inspect(path, inventory)
    except (OSError, ValueError, ET.ParseError) as error: result = {"passed": False, "error": str(error)}
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / f"{suite}-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result)); return 0 if result["passed"] else 1

if __name__ == "__main__": raise SystemExit(main())
