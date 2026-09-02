from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_batch_one_to_larger_sizes_reuses_one_graph",
    "test_hidden_positive_batch_order_reuses_one_graph",
    "test_larger_to_one_to_larger_reuses_one_graph",
    "test_repeated_batch_one_does_not_recompile",
    "test_gathered_logprobs_indices_and_ranks_remain_correct",
    "test_direct_rank_count_correctness",
    "test_mismatched_batch_dimensions_are_rejected",
    "test_empty_batch_is_rejected",
    "test_output_shapes_and_dtypes_are_preserved",
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
