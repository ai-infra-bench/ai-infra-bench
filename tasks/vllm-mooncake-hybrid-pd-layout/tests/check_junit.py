#!/usr/bin/env python3
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


root = ET.parse(sys.argv[1]).getroot()
suites = list(root.iter("testsuite"))
tests = sum(int(suite.attrib.get("tests", "0")) for suite in suites)
failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites)
names = {case.attrib.get("name") for case in root.iter("testcase")}
required = {
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
required.update(
    f"test_non_gdn_mla_shared_storage_preserves_payload_and_neighbors[{ratio}-{kind}]"
    for ratio in (1, 3)
    for kind in ("mla", "sliding_mla")
)
required.update(
    f"test_terminal_attention_payload_completes_without_neighbor_corruption[{ratio}-{endpoint}]"
    for ratio in (1, 5)
    for endpoint in ("source", "destination")
)
required.update(
    f"test_real_scheduler_worker_handoff[{case}]"
    for case in ("cold-token-ids", "two-token-ids", "two-embeddings", "warm-ratio-three", "embedding-ratio-four")
)
required.update(
    f"test_padded_gdn_preserves_payload_and_unrequested_pages[{case}]"
    for case in ("logical-pages", "physical-blocks")
)
assert tests == 38, f"expected exactly 38 tests, got {tests}"
assert failures == 0 and errors == 0 and skipped == 0
assert len(names) == tests, "test case names must be unique"
assert required <= names, f"missing required tests: {required - names}"
