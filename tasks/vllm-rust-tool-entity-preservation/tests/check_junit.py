from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PARSERS = ("minimax_m2", "qwen_coder", "glm_xml", "deepseek_dsml")
SINGLE_PARAMETER_CASES = (
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
)
PARSER_MODE_CASES = (
    "test_numeric_entities_are_preserved_complete_and_streaming",
    "test_entities_are_preserved_for_unrelated_tool_and_parameter",
    "test_existing_whitespace_normalization_is_unchanged",
)
EXPECTED = {
    f"{case}[{parser}]"
    for case in SINGLE_PARAMETER_CASES
    for parser in PARSERS
} | {
    f"{case}[{parser}-{mode}]"
    for case in PARSER_MODE_CASES
    for parser in PARSERS
    for mode in ("complete", "stream")
}


def main() -> None:
    root = ET.parse(Path(sys.argv[1])).getroot()
    cases = root.findall(".//testcase")
    names = [case.attrib["name"] for case in cases]
    assert len(EXPECTED) == 64, EXPECTED
    assert len(names) == len(EXPECTED), names
    assert set(names) == EXPECTED, names
    assert len(names) == len(set(names)), names
    assert not root.findall(".//failure")
    assert not root.findall(".//error")
    assert not root.findall(".//skipped")


if __name__ == "__main__":
    main()
