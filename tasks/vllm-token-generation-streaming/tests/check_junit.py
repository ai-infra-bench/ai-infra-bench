from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


EXPECTED = 10


def main() -> None:
    root = ET.parse(sys.argv[1]).getroot()
    cases = root.findall(".//testcase")
    assert len(cases) == EXPECTED, len(cases)
    assert len({(case.get("classname"), case.get("name")) for case in cases}) == EXPECTED
    assert not root.findall(".//failure")
    assert not root.findall(".//error")
    assert not root.findall(".//skipped")


if __name__ == "__main__":
    main()
