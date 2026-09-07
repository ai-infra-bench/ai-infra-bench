#!/usr/bin/env python3
"""Check exact inventories and completed outcomes without importing candidates."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from case_contract import PIPELINE_CASES, REGRESSION_CASES


def main() -> int:
    path = Path(sys.argv[1])
    suite = sys.argv[2] if len(sys.argv) > 2 else "regression"
    expected = {"regression": REGRESSION_CASES, "pipeline": PIPELINE_CASES}[suite]
    result = {"suite": suite, "expected": len(expected), "passed": False}
    try:
        root = ET.parse(path).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {key: sum(int(s.attrib.get(key, "0")) for s in suites)
                  for key in ("tests", "failures", "errors", "skipped")}
        cases = root.findall(".//testcase")
        names = [case.attrib.get("name", "") for case in cases]
        failed_cases = [name for name, case in zip(names, cases)
                        if any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))]
        valid = (
            bool(suites) and totals["tests"] == len(expected)
            and len(cases) == len(expected) and set(names) == expected
            and totals["failures"] == totals["errors"] == totals["skipped"] == 0
            and not failed_cases
        )
        result.update(passed=valid, **totals, failed_cases=failed_cases,
                      missing=sorted(expected - set(names)), unexpected=sorted(set(names) - expected))
    except (OSError, ValueError, ET.ParseError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / f"{suite}-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
