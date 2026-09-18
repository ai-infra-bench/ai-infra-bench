#!/usr/bin/env python3
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_TESTS = {
    "regression": {
        "test_visible_markers_encoded_as_runtime_pieces[separate]",
        "test_visible_markers_encoded_as_runtime_pieces[single-delta]",
        "test_visible_markers_encoded_as_runtime_pieces[combined-end]",
        "test_visible_markers_encoded_as_runtime_pieces[separate-end]",
        "test_visible_markers_encoded_as_runtime_pieces[unicode]",
        "test_markers_split_across_streaming_deltas[two-parts]",
        "test_markers_split_across_streaming_deltas[uneven]",
        "test_markers_split_across_streaming_deltas[inside-content]",
        "test_markers_split_across_streaming_deltas[many-small-parts]",
        "test_existing_streaming_outputs_remain_unchanged[atomic-separate]",
        "test_existing_streaming_outputs_remain_unchanged[atomic-combined]",
        "test_existing_streaming_outputs_remain_unchanged[plain]",
        "test_incomplete_marker_like_content_remains_visible[less-than]",
        "test_incomplete_marker_like_content_remains_visible[start-prefix-at-finish]",
        "test_incomplete_marker_like_content_remains_visible[invalid-start-prefix]",
        "test_incomplete_marker_like_content_remains_visible[end-prefix]",
        "test_existing_prefilled_reasoning_mode_remains_unchanged[atomic-marker]",
        "test_existing_prefilled_reasoning_mode_remains_unchanged[runtime-pieces]",
        "test_enabled_streaming_with_explicit_atomic_markers_matches_nonstreaming",
        "test_disabled_thinking_mode_remains_plain_content",
        "test_nonstreaming_outputs_remain_unchanged[<mm:think>plan</mm:think>answer-plan-answer]",
        "test_nonstreaming_outputs_remain_unchanged[plain answer-None-plain answer]",
        "test_nonstreaming_outputs_remain_unchanged[</mm:think>answer-None-answer]",
        "test_streaming_reasoning_and_structured_tool_calls[instruction-example]",
        "test_streaming_reasoning_and_structured_tool_calls[different-tool]",
        "test_streaming_reasoning_and_structured_tool_calls[punctuated-argument]",
    },
    "tokenizer": {"test_required_tokenizer_pipeline"},
    "serving": {"test_required_openai_serving_lifecycle"},
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
