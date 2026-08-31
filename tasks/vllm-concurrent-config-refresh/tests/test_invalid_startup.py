#!/usr/bin/env python3
import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path

from transformers import OPTConfig, OPTForCausalLM


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run_case(kind):
    root = Path(tempfile.mkdtemp(prefix=f"invalid-config-{kind}-"))
    config = OPTConfig(
        vocab_size=64, hidden_size=128, ffn_dim=256, num_hidden_layers=1,
        num_attention_heads=4, max_position_embeddings=128,
        word_embed_proj_dim=128, do_layer_norm_before=True,
        pad_token_id=0, bos_token_id=1, eos_token_id=2,
    )
    OPTForCausalLM(config).save_pretrained(root, safe_serialization=True)
    if kind == "missing":
        (root / "config.json").unlink()
    elif kind == "malformed":
        (root / "config.json").write_text("{")
    elif kind == "unsupported":
        (root / "config.json").write_text(json.dumps({
            "model_type": "unsupported_hidden_model",
            "architectures": ["UnsupportedHiddenModel"],
        }))
    log = Path(f"/logs/verifier/invalid_{kind}.log")
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    command = [
        "vllm", "serve", str(root), "--skip-tokenizer-init",
        "--dtype", "float32", "--max-model-len", "64",
        "--num-gpu-blocks-override", "4", "--port", str(port()),
    ]
    with log.open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   env=env)
    try:
        returncode = process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)
        raise AssertionError(f"{kind} configuration did not fail within 15 seconds")
    assert returncode != 0, f"{kind} configuration unexpectedly started"
    assert "Application startup complete" not in log.read_text()
    return {"kind": kind, "returncode": returncode}


def main():
    results = [run_case(kind) for kind in ("missing", "malformed", "unsupported")]
    print(json.dumps({"invalid_startup": results}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
