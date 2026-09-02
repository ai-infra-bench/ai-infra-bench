from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_buffer_reuse_loads_every_simple_parameter",
    "test_buffer_reuse_preserves_pooling_output",
    "test_probed_packed_shard_is_cloned_before_buffer_reuse",
    "test_ordinary_iterator_remains_correct",
    "test_ordinary_packed_iterator_remains_correct",
    "test_relative_checkpoint_names_keep_supported_prefix_mapping",
    "test_missing_output_head_stays_missing",
    "test_unknown_checkpoint_weight_is_ignored_without_corrupting_known_weights",
    "test_loader_does_not_consume_whole_stream_before_parent_reads",
    "test_repeated_buffer_reuse_loads_are_stable",
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
