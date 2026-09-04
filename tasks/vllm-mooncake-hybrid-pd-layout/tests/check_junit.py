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
    "test_physical_block_expansion_copies_only_requested_payload[full]",
    "test_physical_block_expansion_copies_only_requested_payload[mla]",
    "test_registration_failure_is_reported",
    "test_transfer_failure_is_not_reported_as_complete",
    "test_pure_full_attention_transfer_is_unchanged",
    "test_layout_mismatch_is_not_reported_as_complete",
    "test_nixl_hybrid_remote_prefill_behavior_is_unchanged",
    "test_warm_full_prefix_remote_decode_remains_schedulable",
    "test_prompt_embeddings_remote_decode_remains_schedulable",
}
assert tests == 19, f"expected exactly 19 tests, got {tests}"
assert failures == 0 and errors == 0 and skipped == 0
assert len(names) == tests, "test case names must be unique"
assert required <= names, f"missing required tests: {required - names}"
