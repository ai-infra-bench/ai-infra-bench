#!/usr/bin/env python3
"""Run every template configuration independently through the real vLLM server."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from probe_contract import ASSET_HASHES, MODE_SPECS

ASSET_DIR = Path("/opt/models/qwen-template")
LOGS = Path("/logs/verifier")
MODEL_CONFIG = {
    "architectures": ["OPTForCausalLM"], "activation_function": "relu",
    "bos_token_id": 2, "do_layer_norm_before": True, "dtype": "float32",
    "eos_token_id": 2, "ffn_dim": 512, "hidden_size": 256,
    "max_position_embeddings": 1024, "model_type": "opt",
    "num_attention_heads": 4, "num_hidden_layers": 2, "pad_token_id": 1,
    "vocab_size": 248320, "word_embed_proj_dim": 256,
}

STRICT_TEMPLATE = """
{%- set ns = namespace(system_count=0) -%}
{%- for message in messages -%}
  {%- if message.role == 'system' -%}
    {%- set ns.system_count = ns.system_count + 1 -%}
    {%- if not loop.first -%}{{ raise_exception('Inline system turns are not supported by this template') }}{%- endif -%}
  {%- endif -%}
{%- endfor -%}
{%- set merged_system = messages[0].content -%}
{%- if ns.system_count != 1 -%}{{ raise_exception('Expected one leading system message') }}{%- endif -%}
{%- if merged_system.count('LEAD_SENTINEL') != 1 -%}{{ raise_exception('Leading instruction changed') }}{%- endif -%}
{%- if merged_system.count('INLINE_SENTINEL') != 1 -%}{{ raise_exception('Inline instruction changed') }}{%- endif -%}
{%- if merged_system.find('LEAD_SENTINEL') > merged_system.find('INLINE_SENTINEL') -%}{{ raise_exception('System content order changed') }}{%- endif -%}
{%- if messages|length != 4 -%}{{ raise_exception('Conversation message count changed') }}{%- endif -%}
{%- if messages[1].role != 'user' or messages[1].content != 'diagnostic user turn' -%}{{ raise_exception('First user turn changed') }}{%- endif -%}
{%- if messages[2].role != 'assistant' or messages[2].content != 'diagnostic assistant turn' -%}{{ raise_exception('Assistant turn changed') }}{%- endif -%}
{%- if messages[3].role != 'user' or messages[3].content != 'continue' -%}{{ raise_exception('Final user turn changed') }}{%- endif -%}
{%- for message in messages -%}{{ message.role }}:{{ message.content }}
{%- endfor -%}
{%- if add_generation_prompt -%}assistant:{%- endif -%}
"""

PERMISSIVE_TEMPLATE = """
{%- if messages|length != 4 -%}{{ raise_exception('Message count changed') }}{%- endif -%}
{%- if messages[0].role != 'user' or messages[0].content != 'PERMISSIVE_USER_1' -%}{{ raise_exception('First user turn moved') }}{%- endif -%}
{%- if messages[1].role != 'assistant' or messages[1].content != 'PERMISSIVE_ASSISTANT' -%}{{ raise_exception('Assistant turn moved') }}{%- endif -%}
{%- if messages[2].role != 'system' or messages[2].content != 'PERMISSIVE_INLINE_SENTINEL' -%}{{ raise_exception('Inline system position changed') }}{%- endif -%}
{%- if messages[3].role != 'user' or messages[3].content != 'PERMISSIVE_USER_2' -%}{{ raise_exception('Final user turn moved') }}{%- endif -%}
{%- for message in messages -%}{{ message.role }}:{{ message.content }}
{%- endfor -%}
{%- if add_generation_prompt -%}assistant:{%- endif -%}
"""
CONTEXT_TEMPLATE = "{{ strftime_now('%Y') }}\n" + PERMISSIVE_TEMPLATE


def stop_server(process):
    # The API process may already have exited while its engine children live.
    # Always clean the process group, not only a surviving group leader.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def wait_ready(process, root):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited during startup: {process.returncode}")
        try:
            with urllib.request.urlopen(root + "/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    raise TimeoutError("server did not become healthy")


def run_mode(work, mode, index):
    config = MODE_SPECS[mode]
    directory = work / mode
    directory.mkdir()
    family = config["family"]
    template_text = (ASSET_DIR / "chat_template.jinja").read_text() if family == "qwen" else {
        "strict": STRICT_TEMPLATE, "permissive": PERMISSIVE_TEMPLATE,
        "context": CONTEXT_TEMPLATE,
    }[family]
    template = directory / "chat_template.jinja"
    template.write_text(template_text)
    tokenizer_dir = ASSET_DIR
    if config["source"] == "default":
        tokenizer_dir = directory / "tokenizer"
        tokenizer_dir.mkdir()
        for filename in ("config.json", "tokenizer.json"):
            (tokenizer_dir / filename).symlink_to(ASSET_DIR / filename)
        settings = json.loads((ASSET_DIR / "tokenizer_config.json").read_text())
        settings["chat_template"] = template_text
        (tokenizer_dir / "tokenizer_config.json").write_text(json.dumps(settings))
        (tokenizer_dir / "chat_template.jinja").write_text(template_text)

    port = 18080 + index
    address = f"http://127.0.0.1:{port}"
    command = [
        "vllm", "serve", str(work / "model"), "--host", "127.0.0.1", "--port", str(port),
        "--served-model-name", config["model"], "--tokenizer", str(tokenizer_dir),
        "--load-format", "dummy", "--dtype", "float32", "--max-model-len", "1024",
        "--max-num-batched-tokens", "1024", "--max-num-seqs", "8", "--enforce-eager",
    ]
    if config["source"] == "explicit":
        command += ["--chat-template", str(template)]
    environment = dict(os.environ, GLOO_SOCKET_IFNAME="lo", VLLM_CPU_KVCACHE_SPACE="1",
                       VLLM_HOST_IP="127.0.0.1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    with (LOGS / f"{mode}_server.log").open("w") as log:
        process = subprocess.Popen(command, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            wait_ready(process, address)
            probe_env = dict(environment, ANTHROPIC_BASE_URL=address, PROBE_MODE=mode,
                             SERVED_MODEL=config["model"], PROBE_TEMPLATE_PATH=str(template),
                             PYTHONPATH="/tests")
            with (LOGS / f"{mode}_probe.json").open("w") as result:
                probe = subprocess.run(
                    [sys.executable, "/tests/anthropic_sdk_probe.py"], env=probe_env,
                    cwd=work, stdout=result, stderr=subprocess.PIPE, text=True, timeout=300,
                )
            (LOGS / f"{mode}_probe.stderr").write_text(probe.stderr)
            return probe.returncode
        finally:
            stop_server(process)


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    # Fail closed even if a prior invocation left complete-looking results.
    for path in LOGS.glob("*_probe.json"):
        path.unlink()
    for name in ("run-status.json", "check-summary.json"):
        (LOGS / name).unlink(missing_ok=True)
    for filename, expected in ASSET_HASHES.items():
        assert hashlib.sha256((ASSET_DIR / filename).read_bytes()).hexdigest() == expected, filename
    assert not any(p.suffix in {".bin", ".gguf", ".pt", ".pth", ".safetensors"} for p in ASSET_DIR.rglob("*"))
    codes = {}
    errors = {}
    with tempfile.TemporaryDirectory(prefix="anthropic-inline-") as temporary:
        work = Path(temporary)
        (work / "model").mkdir()
        (work / "model/config.json").write_text(json.dumps(MODEL_CONFIG))
        for index, mode in enumerate(MODE_SPECS):
            print(f"Running {mode}", flush=True)
            try:
                codes[mode] = run_mode(work, mode, index)
            except Exception as exc:
                codes[mode] = 1
                errors[mode] = f"{type(exc).__name__}: {exc}"
            print(f"Finished {mode}: {codes[mode]}", flush=True)
    (LOGS / "run-status.json").write_text(json.dumps({
        "completed": True, "exit_codes": codes, "errors": errors,
    }, indent=2) + "\n")
    return 0 if all(code == 0 for code in codes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
