#!/usr/bin/env python3
import asyncio
import json
import os
import re
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
        vocab_size=len(vocab), hidden_size=768, ffn_dim=1536,
        num_hidden_layers=8, num_attention_heads=12, max_position_embeddings=512,
        word_embed_proj_dim=768, do_layer_norm_before=True, pad_token_id=0,
        bos_token_id=2, eos_token_id=3, torch_dtype="float32")).save_pretrained(root)

def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

async def _stream_completion(client: httpx.AsyncClient, root: str, body: dict,
                             started: asyncio.Event | None = None,
                             signal_after_events: int = 1) -> dict:
    token_times = []
    events = 0
    async with client.stream("POST", f"{root}/v1/completions", json=body) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload = json.loads(line.removeprefix("data: "))
            assert len(payload["choices"]) == 1
            events += 1
            token_times.append(time.monotonic())
            if started is not None and events >= signal_after_events:
                started.set()
    return {"events": events, "token_times": token_times}


async def _requests(root: str, model: str):
    incumbent = {
        "model": model,
        "prompt": "checkout incident runbook " * 32,
        "max_tokens": 96,
        "ignore_eos": True,
        "temperature": 0,
        "stream": True,
    }
    long_prompt = {
        "model": model,
        "prompt": "inventory incident runbook " * 112,
        "max_tokens": 4,
        "ignore_eos": True,
        "temperature": 0,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        incumbent_started = asyncio.Event()
        incumbent_task = asyncio.create_task(_stream_completion(
            client, root, incumbent, incumbent_started, signal_after_events=8))
        await asyncio.wait_for(incumbent_started.wait(), timeout=20)
        target_started_at = time.monotonic()
        target_task = asyncio.create_task(_stream_completion(
            client, root, long_prompt))
        incumbent_result, target_result = await asyncio.gather(
            incumbent_task, target_task)
        metrics = (await client.get(f"{root}/metrics")).text

    samples = [float(match.group(1)) for match in re.finditer(
        r"^vllm:num_preemptions(?:_total)?(?:\{[^}]*\})?\s+([0-9.eE+-]+)$",
        metrics,
        re.MULTILINE,
    )]
    assert samples, "vLLM preemption metric is missing"
    preemptions = sum(samples)
    timestamp_pairs = list(zip(
        incumbent_result["token_times"], incumbent_result["token_times"][1:]))
    gaps = [later - earlier for earlier, later in timestamp_pairs]
    baseline_gaps = [later - earlier for earlier, later in timestamp_pairs
                     if later <= target_started_at]
    contended_gaps = [later - earlier for earlier, later in timestamp_pairs
                      if later > target_started_at]
    baseline_gap = sorted(baseline_gaps)[len(baseline_gaps) // 2]
    max_contended_gap = max(contended_gaps, default=0.0)
    gap_ratio = max_contended_gap / max(baseline_gap, 1e-9)
    assert incumbent_result["events"] >= 80
    assert target_result["events"] >= 4
    assert preemptions <= 1
    assert gap_ratio < 3.0
    return {
        "incumbent_events": incumbent_result["events"],
        "target_events": target_result["events"],
        "preemptions": preemptions,
        "max_incumbent_gap_seconds": max(gaps, default=0.0),
        "contended_gap_ratio": gap_ratio,
    }

def main() -> int:
    model_dir = Path(tempfile.mkdtemp(prefix="kv-real-model-"))
    _model(model_dir)
    port = _port()
    log_path = Path("/logs/verifier/real_cpu_server.log")
    env = os.environ.copy()
    env["VLLM_CPU_KVCACHE_SPACE"] = "1"
    env["VLLM_CPU_OMP_THREADS_BIND"] = "nobind"
    env["OMP_NUM_THREADS"] = "1"
    command = ["vllm", "serve", str(model_dir), "--dtype", "float32",
               "--max-model-len", "512", "--max-num-batched-tokens", "64",
               "--enable-chunked-prefill", "--block-size", "32",
               "--num-gpu-blocks-override", "14", "--port", str(port)]
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
        result = asyncio.run(_requests(root, str(model_dir)))
        print(json.dumps({"real_cpu_http": result}), flush=True)
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
