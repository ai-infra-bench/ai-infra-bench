from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_single_bash_command_is_complete",
    "test_text_and_bash_command_both_reach_client",
    "test_parallel_bash_commands_remain_separate",
    "test_unicode_and_escaped_bash_command_is_exact",
    "test_separately_delivered_name_and_arguments_still_work",
    "test_plain_text_stream_is_unchanged",
    "test_reasoning_only_stream_is_unchanged",
    "test_nonstream_text_response_is_unchanged",
    "test_malformed_bash_arguments_are_not_repaired",
    "test_repeated_requests_do_not_share_stream_state",
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
