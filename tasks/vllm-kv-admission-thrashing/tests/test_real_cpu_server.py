#!/usr/bin/env python3
import asyncio
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path
import httpx
from tokenizers import Tokenizer, models, pre_tokenizers
from transformers import OPTConfig, OPTForCausalLM, PreTrainedTokenizerFast

def _model(root: Path) -> None:
    vocab = {"<pad>": 0, "<unk>": 1, "<s>": 2, "</s>": 3,
             "checkout": 4, "incident": 5, "runbook": 6, "inventory": 7}
    tokenizer = Tokenizer(models.WordLevel(vocab, unk_token="<unk>"))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="<unk>",
                            pad_token="<pad>", bos_token="<s>",
                            eos_token="</s>").save_pretrained(root)
    OPTForCausalLM(OPTConfig(
        vocab_size=len(vocab), hidden_size=128, ffn_dim=256,
        num_hidden_layers=1, num_attention_heads=4, max_position_embeddings=512,
        word_embed_proj_dim=128, do_layer_norm_before=True, pad_token_id=0,
        bos_token_id=2, eos_token_id=3, torch_dtype="float32")).save_pretrained(root)

def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

async def _requests(root: str, model: str):
    bodies = [
        {"model": model, "prompt": "checkout incident runbook " * 32,
         "max_tokens": 4, "ignore_eos": True, "temperature": 0},
        {"model": model, "prompt": "inventory incident runbook " * 40,
         "max_tokens": 4, "ignore_eos": True, "temperature": 0},
    ]
    async with httpx.AsyncClient(timeout=30) as client:
        responses = await asyncio.gather(
            *(client.post(f"{root}/v1/completions", json=body) for body in bodies))
    summaries = []
    for response in responses:
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["choices"]) == 1
        assert payload["usage"]["prompt_tokens"] > 0
        assert payload["usage"]["completion_tokens"] > 0
        summaries.append({"status": response.status_code,
                          "prompt_tokens": payload["usage"]["prompt_tokens"],
                          "completion_tokens": payload["usage"]["completion_tokens"]})
    return summaries

def main() -> int:
    model_dir = Path(tempfile.mkdtemp(prefix="kv-real-model-"))
    _model(model_dir)
    port = _port()
    log_path = Path("/logs/verifier/real_cpu_server.log")
    env = os.environ.copy()
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    command = ["vllm", "serve", str(model_dir), "--dtype", "float32",
               "--max-model-len", "256", "--max-num-batched-tokens", "32",
               "--enable-chunked-prefill", "--block-size", "32",
               "--num-gpu-blocks-override", "16", "--port", str(port)]
    with log_path.open("w") as log:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                  env=env)
    try:
        root = f"http://127.0.0.1:{port}"
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError(log_path.read_text())
            try:
                if httpx.get(f"{root}/health", timeout=0.5).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise TimeoutError("CPU vLLM server did not become ready")
        summaries = asyncio.run(_requests(root, str(model_dir)))
        print(json.dumps({"real_cpu_http": summaries}), flush=True)
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

if __name__ == "__main__":
    raise SystemExit(main())
