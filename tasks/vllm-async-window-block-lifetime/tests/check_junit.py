from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_async_swa_holds_blocks_until_output_is_processed",
    "test_async_chunked_local_holds_blocks_until_output_is_processed",
    "test_sync_swa_keeps_immediate_freeing",
    "test_sync_chunked_local_keeps_immediate_freeing",
    "test_async_blocks_are_not_double_freed",
    "test_full_attention_does_not_midflight_free",
    "test_connector_handoff_keeps_inflight_window_blocks",
    "test_competing_load_cannot_reuse_inflight_reader_blocks",
    "test_speculative_rollback_keeps_required_window_blocks",
    "test_async_admission_reserves_for_overlapping_batches",
    "test_pipeline_overlap_holds_window_blocks_and_reserves_capacity",
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
