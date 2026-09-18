#!/usr/bin/env python3
"""Reject skipped, missing, duplicated, or failed verifier cases."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_TESTS = {
    "test_public_video_fixture_is_untampered_and_attributed",
    "test_sintel_public_loader_returns_matching_moments[5]",
    "test_sintel_public_loader_returns_matching_moments[8]",
    "test_sintel_public_loader_returns_matching_moments[13]",
    "test_numbered_h264_uniform_sampling_through_public_loader[profile0]",
    "test_numbered_h264_uniform_sampling_through_public_loader[profile1]",
    "test_numbered_h264_uniform_sampling_through_public_loader[profile2]",
    "test_numbered_h264_uniform_sampling_through_public_loader[profile3]",
    "test_dynamic_loader_fps_and_duration_paths[profile0-3-100]",
    "test_dynamic_loader_fps_and_duration_paths[profile1-4-2]",
    "test_dynamic_loader_fps_and_duration_paths[profile2-2-3]",
    "test_short_video_all_frame_behavior[-1]",
    "test_short_video_all_frame_behavior[20]",
    "test_uniform_loader_combines_frame_and_fps_limits[17-4]",
    "test_uniform_loader_combines_frame_and_fps_limits[40-5]",
    "test_concurrent_public_pyav_decodes_do_not_share_state",
    "test_nemotron_public_loader_returns_matching_moments_and_metadata",
    "test_nonzero_stream_start_returns_target_frames[uniform]",
    "test_nonzero_stream_start_returns_target_frames[dynamic]",
    "test_nonzero_stream_start_returns_target_frames[nemotron]",
    "test_pyav_public_paths_work_without_opencv_importable[opencv-kwargs0]",
    "test_pyav_public_paths_work_without_opencv_importable[opencv_dynamic-kwargs1]",
    "test_pyav_public_paths_work_without_opencv_importable[nemotron_vl-kwargs2]",
}


def main() -> int:
    report = Path(sys.argv[1])
    try:
        root = ET.parse(report).getroot()
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        totals = {
            key: sum(int(suite.attrib.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        cases = root.findall(".//testcase")
        names = [case.attrib.get("name", "") for case in cases]
        valid = (
            bool(suites)
            and totals["tests"] == len(EXPECTED_TESTS)
            and len(cases) == len(EXPECTED_TESTS)
            and set(names) == EXPECTED_TESTS
            and totals["failures"] == totals["errors"] == totals["skipped"] == 0
        )
        result = {
            "expected": len(EXPECTED_TESTS),
            **totals,
            "missing": sorted(EXPECTED_TESTS - set(names)),
            "unexpected": sorted(set(names) - EXPECTED_TESTS),
        }
    except (OSError, ValueError, ET.ParseError) as error:
        valid = False
        result = {"expected": len(EXPECTED_TESTS), "error": str(error)}
    print(result)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
