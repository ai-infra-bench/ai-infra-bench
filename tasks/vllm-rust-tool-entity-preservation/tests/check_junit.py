from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_literal_entities_are_preserved_complete",
    "test_literal_entities_are_preserved_streaming",
    "test_escaped_closing_delimiters_remain_escaped",
    "test_numeric_and_structured_values_keep_schema_conversion",
    "test_typed_values_work_with_streaming_boundaries",
    "test_unknown_and_incomplete_entities_are_unchanged",
    "test_plain_assistant_text_is_preserved",
    "test_multiple_tool_calls_keep_order",
    "test_incomplete_tool_call_reports_an_error",
    "test_ordinary_strings_without_entities_are_unchanged",
}


def main() -> None:
    root = ET.parse(Path(sys.argv[1])).getroot()
    cases = root.findall(".//testcase")
    names = [case.attrib["name"] for case in cases]
    assert len(names) == len(EXPECTED), names
    assert set(names) == EXPECTED, names
    assert len(names) == len(set(names)), names
    assert not root.findall(".//failure")
    assert not root.findall(".//error")
    assert not root.findall(".//skipped")


if __name__ == "__main__":
    main()
