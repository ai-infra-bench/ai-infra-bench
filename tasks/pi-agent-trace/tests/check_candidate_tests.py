#!/usr/bin/env python3
"""Require actual, non-skipped candidate unit-test completion, not merely exit zero."""
import sys
import xml.etree.ElementTree as ET


def main():
    try:
        root = ET.parse(sys.argv[1]).getroot()
        suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
        cases = root.findall(".//testcase")
        if not cases or not suites:
            raise ValueError("candidate test report has no executed cases")
        if any(case.find(tag) is not None for case in cases for tag in ("failure", "error")):
            raise ValueError("candidate tests include failures or errors")
        if not any(case.find("skipped") is None for case in cases):
            raise ValueError("candidate tests are all skipped")
        if sum(int(s.get("tests", "0")) for s in suites) != len(cases):
            raise ValueError("candidate test inventory and totals disagree")
        if any(int(s.get(key, "0")) for s in suites for key in ("failures", "errors")):
            raise ValueError("candidate test suite did not pass")
        print(f"candidate tests: {len(cases)} cases reported, at least one completed")
        return 0
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"candidate tests incomplete: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
