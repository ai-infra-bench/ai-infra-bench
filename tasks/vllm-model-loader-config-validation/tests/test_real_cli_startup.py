from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import torch
from transformers import OPTConfig, OPTForCausalLM


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def pt_only_model() -> Path:
    root = Path(tempfile.mkdtemp(prefix="loader-validation-model-"))
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


def run_failure(
    root: Path,
    name: str,
    extra_args: list[str],
) -> dict:
    log = Path(f"/logs/verifier/cli_{name}.log")
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    command = [
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
        "--port",
        str(free_port()),
        *extra_args,
    ]
    with log.open("w") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    try:
        returncode = process.wait(timeout=45)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        raise AssertionError(f"{name} did not fail within 45 seconds")
    text = log.read_text()
    return {"case": name, "returncode": returncode, "log": text}


def run_success(root: Path, load_format: str) -> dict:
    selected_port = free_port()
    log = Path(f"/logs/verifier/cli_success_{load_format}.log")
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    command = [
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
        load_format,
        "--port",
        str(selected_port),
    ]
    with log.open("w") as output:
        process = subprocess.Popen(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
    try:
        root_url = f"http://127.0.0.1:{selected_port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(log.read_text()[-6000:])
            try:
                if httpx.get(f"{root_url}/health", timeout=0.5).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.25)
        else:
            raise AssertionError(f"{load_format} server did not become healthy")
        return {"case": load_format, "status": 200}
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def main() -> int:
    root = pt_only_model()
    explicit_safetensors = run_failure(
        root,
        "explicit_safetensors",
        ["--load-format", "safetensors"],
    )
    zero_threads = run_failure(
        root,
        "zero_threads",
        [
            "--load-format",
            "pt",
            "--model-loader-extra-config",
            '{"enable_multithread_load":true,"num_threads":0}',
        ],
    )
    successes = [run_success(root, load_format) for load_format in ("auto", "hf", "pt")]
    results = [
        {
            "case": explicit_safetensors["case"],
            "returncode": explicit_safetensors["returncode"],
            "message": "Cannot find any model weights",
        },
        {
            "case": zero_threads["case"],
            "returncode": zero_threads["returncode"],
            "message": "num_threads must be a positive integer",
        },
        *successes,
    ]
    print(json.dumps({"real_vllm_cli": results}, separators=(",", ":")))
    assert explicit_safetensors["returncode"] != 0
    assert "Cannot find any model weights" in explicit_safetensors["log"]
    assert "SafetensorError" not in explicit_safetensors["log"]
    assert zero_threads["returncode"] != 0
    assert "num_threads must be a positive integer" in zero_threads["log"]
    assert "max_workers must be greater than 0" not in zero_threads["log"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
