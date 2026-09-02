from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_late_bias_waits_until_bias_load",
    "test_processing_observes_loaded_bias_value",
    "test_loaded_weight_and_bias_are_both_visible_at_processing",
    "test_two_layers_track_late_bias_independently",
    "test_layer_without_bias_processes_after_weight",
    "test_never_loaded_skip_buffer_does_not_block_processing",
    "test_bias_remains_outside_meta_capture",
    "test_missing_bias_defers_until_finalize",
    "test_processing_runs_exactly_once_after_complete_load",
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
