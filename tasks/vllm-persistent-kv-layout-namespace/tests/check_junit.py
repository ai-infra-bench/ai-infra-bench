#!/usr/bin/env python3
"""Reject missing, duplicated, skipped, or failed verifier cases."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_TESTS = 19
EXPECTED_NAMES = {
    "test_runner_rollout_does_not_reuse_incompatible_cache[v1-to-v2-public-opt]",
    "test_runner_rollout_does_not_reuse_incompatible_cache[v1-to-v2-hidden-model]",
    "test_runner_rollout_does_not_reuse_incompatible_cache[v2-to-v1-public-opt]",
    "test_runner_rollout_does_not_reuse_incompatible_cache[v2-to-v1-hidden-model]",
    "test_same_runner_restart_reuses_valid_cache[v1]",
    "test_same_runner_restart_reuses_valid_cache[v2]",
    "test_incompatible_layouts_do_not_reuse_persistent_blocks[default]",
    "test_incompatible_layouts_do_not_reuse_persistent_blocks[bf16-config]",
    "test_incompatible_layouts_do_not_reuse_persistent_blocks[larger-files]",
    "test_incompatible_layouts_do_not_reuse_persistent_blocks[two-layers]",
    "test_portable_layouts_reopen_and_load_across_parallel_configs[tp]",
    "test_portable_layouts_reopen_and_load_across_parallel_configs[pp]",
    "test_portable_layouts_reopen_and_load_across_parallel_configs[pcp]",
    "test_portable_layouts_reopen_and_load_across_parallel_configs[dcp]",
    "test_layout_specific_parallel_configs_do_not_reuse_files[tp]",
    "test_layout_specific_parallel_configs_do_not_reuse_files[pp]",
    "test_layout_specific_parallel_configs_do_not_reuse_files[context-parallel]",
    "test_model_identity_remains_part_of_persistent_compatibility",
    "test_portable_layout_reads_preexisting_legacy_artifact",
}


def main() -> int:
    root = ET.parse(Path(sys.argv[1])).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    totals = {
        key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    cases = root.findall(".//testcase")
    names = [(case.attrib.get("classname"), case.attrib.get("name")) for case in cases]
    observed_names = {name for _classname, name in names}
    valid = (
        totals["tests"] == EXPECTED_TESTS
        and len(cases) == EXPECTED_TESTS
        and len(set(names)) == EXPECTED_TESTS
        and observed_names == EXPECTED_NAMES
        and totals["failures"] == 0
        and totals["errors"] == 0
        and totals["skipped"] == 0
    )
    print(
        {
            "expected": EXPECTED_TESTS,
            **totals,
            "unique": len(set(names)),
            "expected_names": observed_names == EXPECTED_NAMES,
        }
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
