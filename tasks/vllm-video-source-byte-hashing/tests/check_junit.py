from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_short_encoded_source_changes_hash_when_frames_match",
    "test_long_sources_fall_back_to_smaller_decoded_frames",
    "test_short_sources_are_part_of_cache_identity",
    "test_sampling_metadata_changes_source_based_hash",
    "test_same_source_and_sampling_are_stable",
    "test_bare_decoded_pixel_changes_remain_visible",
    "test_metadata_free_preprocessing_still_returns_frames",
    "test_loaded_video_preserves_tuple_indexing",
    "test_base64_jpeg_frame_lists_remain_compatible",
    "test_image_source_byte_hashing_is_unchanged",
    "test_short_source_hashing_is_materially_cheaper",
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
