from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_large_sync_data_url_avoids_generic_parser_overhead",
    "test_large_async_data_url_avoids_generic_parser_overhead",
    "test_mixed_case_data_scheme_preserves_type_and_payload",
    "test_real_png_decodes_through_sync_and_async_paths",
    "test_http_domain_checks_and_downloads_remain_active",
    "test_file_urls_keep_allowlist_and_traversal_checks",
    "test_unsupported_scheme_still_fails",
    "test_malformed_data_urls_still_fail[data:image/png;base64]",
    "test_malformed_data_urls_still_fail[data:image/png]",
    "test_non_base64_data_url_still_fails",
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
