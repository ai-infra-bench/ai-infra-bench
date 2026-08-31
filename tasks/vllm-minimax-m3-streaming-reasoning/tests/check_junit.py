#!/usr/bin/env python3
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_TESTS = 17


def main() -> int:
    root = ET.parse(Path(sys.argv[1])).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    cases = root.findall(".//testcase")
    names = [(case.attrib.get("classname"), case.attrib.get("name")) for case in cases]
    valid = (
        totals["tests"] == EXPECTED_TESTS
        and len(cases) == EXPECTED_TESTS
        and len(set(names)) == EXPECTED_TESTS
        and totals["failures"] == 0
        and totals["errors"] == 0
        and totals["skipped"] == 0
    )
    print({"expected": EXPECTED_TESTS, **totals, "unique": len(set(names))})
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
