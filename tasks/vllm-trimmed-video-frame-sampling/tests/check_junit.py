#!/usr/bin/env python3
"""Reject skipped, missing, duplicated, unexpected, or failed verifier cases."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import expected_test_names  # noqa: E402


def main() -> int:
    expected = expected_test_names()
    try:
        root = ET.parse(sys.argv[1]).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {
            key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        names = [case.attrib.get("name", "") for case in root.findall(".//testcase")]
        bad_cases = [
            case.attrib.get("name", "")
            for case in root.findall(".//testcase")
            if case.find("failure") is not None
            or case.find("error") is not None
            or case.find("skipped") is not None
        ]
        valid = (
            bool(suites)
            and totals["tests"] == len(expected) == len(names) == len(set(names))
            and set(names) == expected
            and totals["failures"] == totals["errors"] == totals["skipped"] == 0
            and not bad_cases
        )
        result = {
            "expected": len(expected),
            **totals,
            "missing": sorted(expected - set(names))[:20],
            "unexpected": sorted(set(names) - expected)[:20],
            "not_passed": bad_cases[:40],
        }
    except (OSError, ValueError, ET.ParseError) as error:
        valid = False
        result = {"expected": len(expected), "error": str(error)}
    print(result)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
