from __future__ import annotations

import json
import statistics
import subprocess
import sys


SAMPLES = 5
MAX_RATIO = 1.5
MAX_OVERHEAD_SECONDS = 0.8
IMPORT_SCRIPT = r"""
import importlib
import json
import os
import sys
import time

target = sys.argv[1]
started = time.perf_counter()
importlib.import_module(target)
elapsed = time.perf_counter() - started
print(json.dumps({
    "target": target,
    "elapsed": elapsed,
    "benchmark_modules": sorted(
        name for name in sys.modules
        if name.startswith("vllm.entrypoints.cli.benchmark.")
    ),
    "plotting_modules": sorted(
        name for name in sys.modules
        if name.split(".", 1)[0] in {"matplotlib", "pandas", "seaborn"}
    ),
    "inductor_config_loaded": "torch._inductor.config" in sys.modules,
    "compile_threads": os.environ.get("TORCHINDUCTOR_COMPILE_THREADS"),
}))
"""


def measure(target: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_SCRIPT, target],
        cwd="/workspace/vllm",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout.splitlines()[-1])


def main() -> int:
    plain_reports: list[dict[str, object]] = []
    cli_reports: list[dict[str, object]] = []
    for sample in range(SAMPLES):
        # Alternate order so transient host load is not always charged to one side.
        targets = (
            ("vllm", plain_reports),
            ("vllm.entrypoints.cli.main", cli_reports),
        )
        if sample % 2:
            targets = tuple(reversed(targets))
        for target, reports in targets:
            report = measure(target)
            reports.append(report)
            print(json.dumps(report, separators=(",", ":")))

    plain_median = statistics.median(
        float(report["elapsed"]) for report in plain_reports
    )
    cli_median = statistics.median(
        float(report["elapsed"]) for report in cli_reports
    )
    ratio = cli_median / plain_median
    overhead = cli_median - plain_median
    import_contract = all(
        not report["benchmark_modules"]
        and not report["plotting_modules"]
        and report["compile_threads"] == "1"
        for report in cli_reports
    )
    correct = (
        import_contract
        and ratio <= MAX_RATIO
        and overhead <= MAX_OVERHEAD_SECONDS
    )
    summary = {
        "samples_per_target": SAMPLES,
        "plain_import_median_seconds": plain_median,
        "cli_import_median_seconds": cli_median,
        "cli_to_plain_ratio": ratio,
        "cli_overhead_seconds": overhead,
        "max_ratio": MAX_RATIO,
        "max_overhead_seconds": MAX_OVERHEAD_SECONDS,
        "import_contract": import_contract,
        "cold_cli_import_contract": correct,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if correct else 3


if __name__ == "__main__":
    raise SystemExit(main())
