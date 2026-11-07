import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    report = Path(sys.argv[1])
    expected = int(sys.argv[2])
    if not report.is_file() or report.stat().st_size == 0:
        raise AssertionError(f"missing JUnit report: {report}")

    root = ET.parse(report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise AssertionError("JUnit report contains no testsuite")
    suite = suites[0]
    values = {
        key: int(suite.get(key, "0"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    if values["tests"] != expected:
        raise AssertionError(f"expected {expected} tests, got {values}")
    if any(values[key] for key in ("failures", "errors", "skipped")):
        raise AssertionError(f"JUnit suite was not fully successful: {values}")
    print(f"verified JUnit inventory: {values}")


if __name__ == "__main__":
    main()
