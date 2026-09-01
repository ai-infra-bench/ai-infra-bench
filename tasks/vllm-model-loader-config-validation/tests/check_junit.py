from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_non_string_load_formats_are_rejected_early",
    "test_unknown_safetensors_strategies_are_rejected",
    "test_supported_safetensors_strategies_remain_valid",
    "test_extra_config_must_be_a_mapping",
    "test_multithread_flag_must_be_boolean",
    "test_invalid_thread_counts_are_rejected_at_loader_construction",
    "test_positive_thread_counts_remain_valid",
    "test_multithread_rejects_non_lazy_strategies",
    "test_multithread_default_and_lazy_strategies_remain_valid",
    "test_custom_string_load_format_remains_extensible",
    "test_unknown_extra_keys_are_still_rejected",
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
