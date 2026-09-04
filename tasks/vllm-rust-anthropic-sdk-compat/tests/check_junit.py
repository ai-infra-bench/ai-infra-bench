from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main() -> int:
    path = sys.argv[1]
    expected = int(sys.argv[2])
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
    names = [case.attrib.get("name", "") for case in root.iter("testcase")]
    print(
        {
            "path": path,
            "tests": tests,
            "expected": expected,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "unique_names": len(set(names)),
        }
    )
    return 0 if (
        tests == expected
        and len(names) == expected
        and len(set(names)) == expected
        and failures == 0
        and errors == 0
        and skipped == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
