#!/usr/bin/env python3
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


REGRESSION_REQUIRED = {
    "test_hybrid_worker_initializes_and_registers_through_connector",
    "test_hybrid_transfer_preserves_group_payloads[full]",
    "test_hybrid_transfer_preserves_group_payloads[mla]",
    "test_shared_padded_storage_transfers_without_neighbor_corruption",
    "test_cross_group_shared_backing_preserves_all_transfer_regions",
    "test_partial_prefix_transfers_requested_suffix_per_group",
    "test_physical_block_expansion_copies_only_requested_payload[full]",
    "test_physical_block_expansion_copies_only_requested_payload[mla]",
    "test_transfer_failure_is_not_reported_as_complete",
    "test_pure_full_attention_transfer_is_unchanged",
    "test_layout_mismatch_is_not_reported_as_complete",
    "test_nixl_hybrid_remote_prefill_behavior_is_unchanged",
    "test_prompt_embeddings_remote_prefill_uses_remote_state_then_resumes",
    "test_two_element_gdn_remote_decode_boundary[token_ids]",
    "test_two_element_gdn_remote_decode_boundary[prompt_embeddings]",
    "test_warm_full_prefix_remote_decode_remains_schedulable",
    "test_prompt_embeddings_remote_decode_remains_schedulable",
}
REGRESSION_REQUIRED.update(
    f"test_non_gdn_mla_shared_storage_preserves_payload_and_neighbors[{ratio}-{kind}]"
    for ratio in (1, 3)
    for kind in ("mla", "sliding_mla")
)
REGRESSION_REQUIRED.update(
    f"test_terminal_attention_payload_completes_without_neighbor_corruption[{ratio}-{endpoint}]"
    for ratio in (1, 5)
    for endpoint in ("source", "destination")
)


def main() -> int:
    suite = sys.argv[2] if len(sys.argv) > 2 else "regression"
    required = (
        {"test_required_inmemory_pd_transfer"}
        if suite == "pipeline"
        else REGRESSION_REQUIRED
    )
    expected_count = 1 if suite == "pipeline" else 31
    try:
        root = ET.parse(Path(sys.argv[1])).getroot()
        suites = list(root.iter("testsuite"))
        tests = sum(int(item.attrib.get("tests", "0")) for item in suites)
        failures = sum(int(item.attrib.get("failures", "0")) for item in suites)
        errors = sum(int(item.attrib.get("errors", "0")) for item in suites)
        skipped = sum(int(item.attrib.get("skipped", "0")) for item in suites)
        names = [case.attrib.get("name", "") for case in root.iter("testcase")]
        valid = (
            bool(suites)
            and tests == expected_count
            and len(names) == expected_count
            and len(set(names)) == expected_count
            and required <= set(names)
            and failures == errors == skipped == 0
        )
        result = {
            "suite": suite,
            "expected": expected_count,
            "tests": tests,
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
            "missing": sorted(required - set(names)),
        }
    except (OSError, ValueError, ET.ParseError) as error:
        valid = False
        result = {"suite": suite, "expected": expected_count, "error": str(error)}
    print(result)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
