#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED_TESTS = {
    "test_valid_local_configuration_loads",
    "test_persistent_invalid_configuration_fails[missing]",
    "test_persistent_invalid_configuration_fails[malformed]",
    "test_persistent_invalid_configuration_fails[unsupported]",
}

def main() -> int:
    try:
        root = ET.parse(Path(sys.argv[1])).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {key: sum(int(s.attrib.get(key, "0")) for s in suites)
                  for key in ("tests", "failures", "errors", "skipped")}
        cases = root.findall(".//testcase")
        names = [case.attrib.get("name", "") for case in cases]
        valid = (
            bool(suites)
            and totals["tests"] == len(EXPECTED_TESTS)
            and len(cases) == len(EXPECTED_TESTS)
            and set(names) == EXPECTED_TESTS
            and totals["failures"] == totals["errors"] == totals["skipped"] == 0
        )
        result = {
            "expected": len(EXPECTED_TESTS),
            **totals,
            "missing": sorted(EXPECTED_TESTS - set(names)),
            "unexpected": sorted(set(names) - EXPECTED_TESTS),
        }
    except (OSError, ValueError, ET.ParseError) as error:
        valid = False
        result = {"expected": len(EXPECTED_TESTS), "error": str(error)}
    print(result)
    return 0 if valid else 1

if __name__ == "__main__":
    raise SystemExit(main())
