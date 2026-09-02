from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_glm_korean_transition_preserves_unicode",
    "test_qwen_korean_transition_preserves_unicode",
    "test_chunk_size_two_preserves_unicode_for_both_parsers",
    "test_single_batch_transition_preserves_unicode_for_both_parsers",
    "test_consecutive_byte_fallback_tokens_are_not_deleted",
    "test_emoji_bytes_at_transition_are_preserved",
    "test_ascii_transition_remains_unchanged",
    "test_reasoning_only_finish_remains_reasoning",
    "test_empty_content_after_transition_does_not_emit_replacement",
    "test_deferred_whitespace_at_transition_is_flushed",
    "test_unicode_content_with_tools_enabled_stays_content",
    "test_chunk_size_matrix_is_invariant",
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
