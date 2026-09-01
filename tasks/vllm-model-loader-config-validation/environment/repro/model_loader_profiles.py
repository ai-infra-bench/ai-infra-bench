from __future__ import annotations

import os
import socket
import subprocess
import tempfile
from pathlib import Path

import torch
from transformers import OPTConfig, OPTForCausalLM

from vllm.config.load import LoadConfig
from vllm.model_executor.model_loader import get_model_loader


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def model() -> Path:
    root = Path(tempfile.mkdtemp(prefix="pt-only-model-"))
    config = OPTConfig(
        vocab_size=32,
        hidden_size=64,
        ffn_dim=128,
        num_hidden_layers=1,
        num_attention_heads=4,
        max_position_embeddings=128,
        word_embed_proj_dim=64,
        pad_token_id=0,
        bos_token_id=1,
        eos_token_id=2,
    )
    config.architectures = ["OPTForCausalLM"]
    config.save_pretrained(root)
    torch.save(OPTForCausalLM(config).state_dict(), root / "model.pt")
    return root


def constructor_case(name: str, callback) -> bool:
    try:
        callback()
    except Exception as error:
        print(f"{name}: {type(error).__name__}: {error}")
        return True
    print(f"{name}: accepted")
    return False


def cli_case(root: Path, name: str, args: list[str]) -> str:
    log = Path(tempfile.mktemp(prefix=f"{name}-", suffix=".log"))
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
        str(port()),
        *args,
    ]
    with log.open("w") as output:
        process = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=45,
        )
    text = log.read_text()
    interesting = text.splitlines()[-1] if text.splitlines() else "no output"
    for marker in (
        "SafetensorError",
        "Cannot find any model weights",
        "max_workers must be greater than 0",
        "num_threads must be a positive integer",
    ):
        match = next(
            (line for line in reversed(text.splitlines()) if marker in line),
            None,
        )
        if match is not None:
            interesting = match
            break
    print(f"{name}: exit={process.returncode}: {interesting}")
    return text


def main() -> int:
    invalid_format_rejected = constructor_case(
        "load_format=123",
        lambda: LoadConfig(load_format=123),
    )
    invalid_strategy_rejected = constructor_case(
        "safetensors_load_strategy=prefecth",
        lambda: LoadConfig(safetensors_load_strategy="prefecth"),
    )
    zero_threads_rejected = constructor_case(
        "num_threads=0",
        lambda: get_model_loader(
            LoadConfig(
                model_loader_extra_config={
                    "enable_multithread_load": True,
                    "num_threads": 0,
                }
            )
        ),
    )
    root = model()
    safe_log = cli_case(root, "explicit-safetensors", ["--load-format", "safetensors"])
    correct = (
        invalid_format_rejected
        and invalid_strategy_rejected
        and zero_threads_rejected
        and "Cannot find any model weights" in safe_log
        and "SafetensorError" not in safe_log
    )
    print(f"profiles_rejected_early={correct}")
    return 0 if correct else 3


if __name__ == "__main__":
    raise SystemExit(main())
