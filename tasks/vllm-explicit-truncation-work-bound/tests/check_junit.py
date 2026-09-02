from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_left_truncation_bounds_tokenizer_input_and_keeps_suffix",
    "test_right_truncation_bounds_tokenizer_input_and_keeps_prefix",
    "test_character_bound_respects_tokenizer_ratio",
    "test_async_renderer_uses_same_bounded_input",
    "test_no_truncation_still_rejects_oversized_text",
    "test_tokenizer_default_truncation_retains_existing_bound",
    "test_without_context_limit_does_not_invent_a_bound",
    "test_token_list_input_is_unchanged",
    "test_lowercase_and_special_token_options_remain_active",
}


def main() -> None:
    root = ET.parse(Path(sys.argv[1])).getroot()
    names = [case.attrib["name"] for case in root.findall(".//testcase")]
    assert len(names) == len(EXPECTED), names
    assert set(names) == EXPECTED, names
    assert len(names) == len(set(names)), names
    assert not root.findall(".//failure")
    assert not root.findall(".//error")
    assert not root.findall(".//skipped")


if __name__ == "__main__":
    main()
