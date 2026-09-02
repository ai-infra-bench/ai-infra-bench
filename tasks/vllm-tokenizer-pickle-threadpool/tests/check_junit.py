from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_pickle_roundtrip_returns_tokenizer_not_none",
    "test_pickle_roundtrip_preserves_encoding",
    "test_pickle_roundtrip_preserves_decoding",
    "test_restored_tokenizer_remains_thread_safe",
    "test_spawned_process_receives_usable_tokenizer",
    "test_cloudpickle_roundtrip_is_usable",
    "test_multiple_pickle_protocols_are_supported",
    "test_configured_pool_size_survives_roundtrip",
    "test_repeated_wrapping_is_idempotent",
    "test_non_fast_object_keeps_existing_behavior",
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
