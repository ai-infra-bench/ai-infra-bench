from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_prometheus_exposes_capacity_and_deferred",
    "test_existing_total_equals_reason_sum",
    "test_zero_reason_series_are_present",
    "test_each_engine_keeps_its_own_breakdown",
    "test_log_reports_total_and_nonzero_deferred",
    "test_log_omits_deferred_when_zero",
    "test_aggregated_log_sums_both_populations",
    "test_existing_running_and_cache_metrics_remain",
    "test_observability_change_preserves_fcfs_scheduling",
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
