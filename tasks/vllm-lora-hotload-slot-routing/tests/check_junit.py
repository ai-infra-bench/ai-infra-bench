from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_live_slot_swap_preserves_each_requested_adapter",
    "test_three_token_batch_preserves_repeated_adapter_ids",
    "test_mapping_change_without_slot_change_still_routes_correctly",
    "test_repeated_mapping_without_slot_change_is_stable",
    "test_single_adapter_routing_remains_correct",
    "test_unactivated_registration_does_not_change_live_routing",
    "test_multiple_eviction_cycles_follow_current_slot_order",
    "test_reversed_live_batch_survives_slot_swap",
    "test_base_model_tokens_remain_unadapted",
    "test_eviction_keeps_registered_adapters_available",
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
