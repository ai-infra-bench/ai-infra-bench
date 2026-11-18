from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET


def main():
    root = ET.parse(sys.argv[1]).getroot()
    expected = int(sys.argv[2])
    cases = list(root.iter("testcase"))
    suites = list(root.iter("testsuite"))
    identities = [(c.get("classname", ""), c.get("name", "")) for c in cases]
    record = {
        "expected": expected,
        "cases": len(cases),
        "unique_cases": len(set(identities)),
        "reported_tests": sum(int(s.get("tests", 0)) for s in suites),
        "failures": sum(int(s.get("failures", 0)) for s in suites),
        "errors": sum(int(s.get("errors", 0)) for s in suites),
        "skipped": sum(int(s.get("skipped", 0)) for s in suites),
    }
    print(json.dumps(record, sort_keys=True))
    return 0 if (
        record["cases"] == record["unique_cases"] == record["reported_tests"] == expected
        and all(record[key] == 0 for key in ["failures", "errors", "skipped"])
        and not any(c.find(tag) is not None for c in cases for tag in ["failure", "error", "skipped"])
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
