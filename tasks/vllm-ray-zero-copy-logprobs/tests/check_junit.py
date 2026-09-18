#!/usr/bin/env python3
"""Reject skipped, missing, duplicated, or failed verifier cases."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_TESTS = {
    "regression": {
        "test_logprob_values_survive_result_boundary[profile0]",
        "test_logprob_values_survive_result_boundary[profile1]",
        "test_logprob_values_survive_result_boundary[profile2]",
        "test_logprob_values_survive_result_boundary[profile3]",
        "test_repeated_results_do_not_mix_payloads[profile0]",
        "test_repeated_results_do_not_mix_payloads[profile1]",
        "test_repeated_results_do_not_mix_payloads[profile2]",
        "test_repeated_results_do_not_mix_payloads[profile3]",
        "test_empty_logprob_payload_is_valid",
        "test_none_logprobs_and_unrelated_fields_are_preserved",
        "test_downstream_logprob_processing_accepts_result_payload",
        "test_completion_response_preserves_text_tokens_and_logprobs",
        "test_completion_response_preserves_zero_requested_logprobs",
    },
    "ray-channel": {"test_required_ray_executor_channel"},
}


def main() -> int:
    suite = sys.argv[2] if len(sys.argv) > 2 else "regression"
    expected = EXPECTED_TESTS[suite]
    try:
        root = ET.parse(Path(sys.argv[1])).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {
            key: sum(int(item.attrib.get(key, "0")) for item in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        cases = root.findall(".//testcase")
        names = [case.attrib.get("name", "") for case in cases]
        valid = (
            bool(suites)
            and totals["tests"] == len(expected)
            and len(cases) == len(expected)
            and set(names) == expected
            and totals["failures"] == totals["errors"] == totals["skipped"] == 0
        )
        result = {
            "suite": suite,
            "expected": len(expected),
            **totals,
            "missing": sorted(expected - set(names)),
            "unexpected": sorted(set(names) - expected),
        }
    except (OSError, ValueError, ET.ParseError) as error:
        valid = False
        result = {"suite": suite, "expected": len(expected), "error": str(error)}
    print(result)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
