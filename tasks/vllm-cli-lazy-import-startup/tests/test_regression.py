from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path


ROOT = "/workspace/vllm"
HEAVY_PLOT_PREFIXES = ("matplotlib", "pandas", "seaborn", "scipy", "sklearn")


def python_report(statement: str) -> dict:
    code = f"""
import builtins
import json
import os
import sys
import time
attempted = []
original_import = builtins.__import__
def traced_import(name, *args, **kwargs):
    attempted.append(name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = traced_import
started = time.perf_counter()
{statement}
elapsed = time.perf_counter() - started
print(json.dumps({{
    "elapsed": elapsed,
    "modules": sorted(sys.modules),
    "imports": attempted,
    "compile_threads": os.environ.get("TORCHINDUCTOR_COMPILE_THREADS"),
}}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout.splitlines()[-1])


def has_prefix(modules: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for module in modules
        for prefix in prefixes
    )


def write_sweep_results(root: Path) -> None:
    records = [
        {
            "total_token_throughput": 100.0,
            "median_ttft_ms": 40.0,
            "output_throughput": 80.0,
            "max_concurrency": 4,
            "tensor_parallel_size": 1,
        },
        {
            "total_token_throughput": 140.0,
            "median_ttft_ms": 55.0,
            "output_throughput": 112.0,
            "max_concurrency": 8,
            "tensor_parallel_size": 1,
        },
    ]
    (root / "summary.json").write_text(json.dumps(records))


def run_command(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(args),
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout[-6000:]
    return result.stdout


def test_cli_package_import_does_not_load_benchmark_shims() -> None:
    report = python_report("import vllm.entrypoints.cli")
    assert not any(
        module.startswith("vllm.entrypoints.cli.benchmark.")
        for module in report["modules"]
    )


def test_cli_main_import_avoids_plotting_stack() -> None:
    report = python_report("import vllm.entrypoints.cli.main")
    assert not has_prefix(report["imports"], HEAVY_PLOT_PREFIXES)


def test_compile_thread_environment_contract_is_preserved() -> None:
    report = python_report("import vllm")
    assert report["compile_threads"] == "1"


def test_inductor_observes_single_compile_thread() -> None:
    report = python_report(
        "import vllm;"
        "import torch._inductor.config as inductor_config;"
        "assert inductor_config.compile_threads == 1"
    )
    assert report["compile_threads"] == "1"


def test_sweep_modules_do_not_import_optional_plotting_dependencies() -> None:
    for module in (
        "vllm.benchmarks.sweep.plot",
        "vllm.benchmarks.sweep.plot_pareto",
    ):
        report = python_report(f"import {module}")
        assert not has_prefix(report["imports"], ("matplotlib", "pandas", "seaborn"))


def test_public_sweep_plot_commands_generate_pngs(tmp_path: Path) -> None:
    write_sweep_results(tmp_path)
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(tmp_path / "mplconfig")
    run_command(
        "vllm",
        "bench",
        "sweep",
        "plot",
        str(tmp_path),
        "--fig-dir",
        "figures",
        "--fig-name",
        "smoke",
        "--fig-dpi",
        "80",
        "--no-error-bars",
        env=env,
    )
    run_command(
        "vllm",
        "bench",
        "sweep",
        "plot_pareto",
        str(tmp_path),
        env=env,
    )
    for figure in (
        tmp_path / "figures" / "smoke.png",
        tmp_path / "pareto" / "PARETO.png",
    ):
        assert figure.is_file()
        assert figure.stat().st_size > 1000


def test_cli_main_relative_import_overhead_stays_within_budget() -> None:
    plain: list[float] = []
    cli: list[float] = []
    for sample in range(5):
        targets = (("import vllm", plain), ("import vllm.entrypoints.cli.main", cli))
        if sample % 2:
            targets = tuple(reversed(targets))
        for statement, samples in targets:
            samples.append(float(python_report(statement)["elapsed"]))
    plain_median = statistics.median(plain)
    cli_median = statistics.median(cli)
    assert cli_median / plain_median <= 1.5, {"plain": plain, "cli": cli}
    assert cli_median - plain_median <= 0.8, {"plain": plain, "cli": cli}
