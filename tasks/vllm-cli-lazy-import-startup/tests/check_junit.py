from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPECTED = {
    "test_cli_package_import_does_not_load_benchmark_shims",
    "test_cli_main_import_avoids_plotting_stack",
    "test_compile_thread_environment_contract_is_preserved",
    "test_inductor_observes_single_compile_thread",
    "test_sweep_modules_do_not_import_optional_plotting_dependencies",
    "test_public_sweep_plot_commands_generate_pngs",
    "test_cli_main_relative_import_overhead_stays_within_budget",
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
