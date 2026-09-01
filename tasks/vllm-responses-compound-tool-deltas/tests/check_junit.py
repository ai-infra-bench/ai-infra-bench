from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_name_and_first_arguments_in_one_delta",
    "test_all_argument_fragments_from_same_model_step",
    "test_content_and_tool_update_keep_event_order",
    "test_reasoning_content_and_tool_update_are_all_preserved",
    "test_parallel_tools_in_one_delta_do_not_mix_arguments",
    "test_unicode_and_escaped_arguments_are_byte_exact",
    "test_separate_name_and_argument_deltas_still_work",
    "test_plain_text_stream_is_unchanged",
    "test_reasoning_only_stream_is_unchanged",
    "test_empty_tool_open_does_not_duplicate_items",
    "test_nonstream_text_response_is_unchanged",
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
