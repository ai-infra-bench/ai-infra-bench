from __future__ import annotations

import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import torch
from transformers import OPTConfig, OPTForCausalLM


ROOT = "/workspace/vllm"


def command(*args: str, env: dict[str, str] | None = None) -> str:
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


def import_report(target: str) -> dict[str, object]:
    code = r"""
import importlib
import json
import os
import sys
import time
target = sys.argv[1]
started = time.perf_counter()
importlib.import_module(target)
print(json.dumps({
    "elapsed": time.perf_counter() - started,
    "benchmark_modules_loaded": any(
        name.startswith("vllm.entrypoints.cli.benchmark.")
        for name in sys.modules
    ),
    "plotting_modules_loaded": any(
        name.split(".", 1)[0] in {"matplotlib", "pandas", "seaborn"}
        for name in sys.modules
    ),
    "compile_threads": os.environ.get("TORCHINDUCTOR_COMPILE_THREADS"),
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, target],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout.splitlines()[-1])


def paired_import_profile() -> dict[str, object]:
    plain_reports: list[dict[str, object]] = []
    cli_reports: list[dict[str, object]] = []
    for sample in range(5):
        targets = (("vllm", plain_reports), ("vllm.entrypoints.cli.main", cli_reports))
        if sample % 2:
            targets = tuple(reversed(targets))
        for target, reports in targets:
            reports.append(import_report(target))
    plain_times = [float(report["elapsed"]) for report in plain_reports]
    cli_times = [float(report["elapsed"]) for report in cli_reports]
    plain_median = statistics.median(plain_times)
    cli_median = statistics.median(cli_times)
    return {
        "plain_seconds": plain_times,
        "cli_seconds": cli_times,
        "plain_median_seconds": plain_median,
        "cli_median_seconds": cli_median,
        "cli_to_plain_ratio": cli_median / plain_median,
        "cli_overhead_seconds": cli_median - plain_median,
        "imports_are_lazy": all(
            not report["benchmark_modules_loaded"]
            and not report["plotting_modules_loaded"]
            and report["compile_threads"] == "1"
            for report in cli_reports
        ),
    }


def plot_smoke() -> dict[str, int]:
    root = Path(tempfile.mkdtemp(prefix="cli-sweep-plots-"))
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
    env = os.environ.copy()
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(root / "mplconfig")
    command(
        "vllm",
        "bench",
        "sweep",
        "plot",
        str(root),
        "--fig-dir",
        "figures",
        "--fig-name",
        "smoke",
        "--fig-dpi",
        "80",
        "--no-error-bars",
        env=env,
    )
    command("vllm", "bench", "sweep", "plot_pareto", str(root), env=env)
    figures = (
        root / "figures" / "smoke.png",
        root / "pareto" / "PARETO.png",
    )
    sizes = {figure.name: figure.stat().st_size for figure in figures}
    assert all(size > 1000 for size in sizes.values()), sizes
    return sizes


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def tiny_opt_checkpoint() -> Path:
    root = Path(tempfile.mkdtemp(prefix="cli-lazy-opt-"))
    config = OPTConfig(
        vocab_size=64,
        hidden_size=64,
        ffn_dim=128,
        num_hidden_layers=1,
        num_attention_heads=4,
        max_position_embeddings=128,
        word_embed_proj_dim=64,
        do_layer_norm_before=True,
        pad_token_id=0,
        bos_token_id=1,
        eos_token_id=2,
    )
    config.architectures = ["OPTForCausalLM"]
    config.save_pretrained(root)
    torch.save(OPTForCausalLM(config).state_dict(), root / "model.pt")
    return root


def serve_smoke() -> dict[str, object]:
    root = tiny_opt_checkpoint()
    selected_port = free_port()
    log = Path("/logs/verifier/real_serve.log")
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    with log.open("w") as output:
        process = subprocess.Popen(
            [
                "vllm",
                "serve",
                str(root),
                "--skip-tokenizer-init",
                "--dtype",
                "float32",
                "--max-model-len",
                "64",
                "--num-gpu-blocks-override",
                "4",
                "--load-format",
                "pt",
                "--port",
                str(selected_port),
            ],
            cwd=ROOT,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    try:
        deadline = time.monotonic() + 75
        health_url = f"http://127.0.0.1:{selected_port}/health"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(log.read_text()[-6000:])
            try:
                response = httpx.get(health_url, timeout=0.5)
                if response.status_code == 200:
                    return {"health_status": 200, "port": selected_port}
            except Exception:
                pass
            time.sleep(0.25)
        raise AssertionError("CPU vllm serve did not become healthy within 75 seconds")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def main() -> int:
    root_help = command("vllm", "--help")
    assert "bench" in root_help and "serve" in root_help
    serve_help = command("vllm", "serve", "--help")
    assert "usage:" in serve_help.lower()
    version = command("vllm", "--version").splitlines()[-1]
    assert version

    bench_help = command("vllm", "bench", "--help")
    subcommands = ["latency", "mm-processor", "serve", "startup", "sweep", "throughput"]
    for subcommand in subcommands:
        assert subcommand in bench_help
        output = command("vllm", "bench", subcommand, "--help")
        assert "usage:" in output.lower()

    sweep_help = command("vllm", "bench", "sweep", "--help")
    assert "plot" in sweep_help
    for plot_command in ("plot", "plot_pareto"):
        output = command("vllm", "bench", "sweep", plot_command, "--help")
        assert "usage:" in output.lower()

    plot_outputs = plot_smoke()
    server = serve_smoke()
    profile = paired_import_profile()
    report = {
        "entrypoints": {
            "root_help": True,
            "serve_help": True,
            "version": version,
            "bench_subcommands": subcommands,
            "sweep_plot_commands": ["plot", "plot_pareto"],
        },
        "plot_png_sizes": plot_outputs,
        "serve": server,
        "paired_import_profile": profile,
    }
    print(json.dumps(report, separators=(",", ":")))
    assert profile["imports_are_lazy"], profile
    assert float(profile["cli_to_plain_ratio"]) <= 1.5, profile
    assert float(profile["cli_overhead_seconds"]) <= 0.8, profile
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
