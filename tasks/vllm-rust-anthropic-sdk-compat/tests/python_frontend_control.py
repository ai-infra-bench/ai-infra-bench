from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import anthropic


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(port: int, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(log_path.read_text())
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=1
            ) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(1)
    raise AssertionError(f"Python frontend did not become ready:\n{log_path.read_text()}")


def write_model(path: Path) -> None:
    path.mkdir()
    (path / "config.json").write_text(
        json.dumps(
            {
                "architectures": ["OPTForCausalLM"],
                "activation_function": "relu",
                "bos_token_id": 2,
                "do_layer_norm_before": True,
                "dtype": "float32",
                "eos_token_id": 2,
                "ffn_dim": 512,
                "hidden_size": 256,
                "max_position_embeddings": 1024,
                "model_type": "opt",
                "num_attention_heads": 4,
                "num_hidden_layers": 2,
                "pad_token_id": 1,
                "vocab_size": 248320,
                "word_embed_proj_dim": 256,
            }
        )
    )


def main() -> int:
    assert importlib.metadata.version("anthropic") == "1.3.0"
    with tempfile.TemporaryDirectory(prefix="anthropic-python-control-") as raw_root:
        root = Path(raw_root)
        model = root / "model"
        log_path = root / "server.log"
        write_model(model)
        port = free_port()
        environment = os.environ.copy()
        environment.pop("VLLM_USE_RUST_FRONTEND", None)
        environment.update(
            {
                "GLOO_SOCKET_IFNAME": "lo",
                "VLLM_CPU_KVCACHE_SPACE": "1",
                "VLLM_HOST_IP": "127.0.0.1",
            }
        )
        with log_path.open("w") as log:
            process = subprocess.Popen(
                [
                    "vllm",
                    "serve",
                    str(model),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--served-model-name",
                    "local-model",
                    "--tokenizer",
                    "/opt/models/qwen-template",
                    "--chat-template",
                    "/opt/models/qwen-template/chat_template.jinja",
                    "--enable-auto-tool-choice",
                    "--tool-call-parser",
                    "qwen3_coder",
                    "--load-format",
                    "dummy",
                    "--dtype",
                    "float32",
                    "--max-model-len",
                    "1024",
                    "--max-num-batched-tokens",
                    "1024",
                    "--max-num-seqs",
                    "8",
                    "--enforce-eager",
                ],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        try:
            wait_ready(port, process, log_path)
            sdk = anthropic.Anthropic(
                api_key="control-key",
                base_url=f"http://127.0.0.1:{port}",
                max_retries=0,
                timeout=60,
                _strict_response_validation=True,
            )
            basic = sdk.messages.create(
                model="local-model",
                max_tokens=1,
                messages=[{"role": "user", "content": "CONTROL_BASIC"}],
            )
            system = sdk.messages.create(
                model="local-model",
                max_tokens=1,
                system="CONTROL_SYSTEM",
                messages=[{"role": "user", "content": "CONTROL_USER"}],
            )
            system_blocks = sdk.messages.create(
                model="local-model",
                max_tokens=1,
                system=[{"type": "text", "text": "CONTROL_SYSTEM_BLOCK"}],
                messages=[{"role": "user", "content": "CONTROL_BLOCK_USER"}],
            )
            raw = sdk.messages.with_raw_response.create(
                model="local-model",
                max_tokens=1,
                messages=[{"role": "user", "content": "CONTROL_RAW"}],
            )
            raw_message = raw.parse()
            weather_tool = {
                "name": "get_weather",
                "description": "Return weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
            tools = sdk.messages.create(
                model="local-model",
                max_tokens=1,
                messages=[{"role": "user", "content": "CONTROL_TOOLS"}],
                tools=[weather_tool],
                tool_choice={"type": "auto"},
            )
            tool_history = sdk.messages.create(
                model="local-model",
                max_tokens=1,
                messages=[
                    {"role": "user", "content": "CONTROL_TOOL_HISTORY_USER"},
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_control",
                                "name": "get_weather",
                                "input": {"city": "Paris"},
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_control",
                                "content": "21 C",
                            }
                        ],
                    },
                ],
                tools=[weather_tool],
            )
            count = sdk.messages.count_tokens(
                model="local-model",
                system="CONTROL_SYSTEM",
                messages=[{"role": "user", "content": "CONTROL_COUNT"}],
            )
            count_tools = sdk.messages.count_tokens(
                model="local-model",
                system="CONTROL_COUNT_SYSTEM",
                messages=[{"role": "user", "content": "CONTROL_COUNT_TOOLS"}],
                tools=[weather_tool],
            )
            with sdk.messages.stream(
                model="local-model",
                max_tokens=1,
                messages=[{"role": "user", "content": "CONTROL_STREAM"}],
            ) as stream:
                events = list(stream)
                streamed = stream.get_final_message()

            async def async_control() -> bool:
                async with anthropic.AsyncAnthropic(
                    api_key="control-key",
                    base_url=f"http://127.0.0.1:{port}",
                    max_retries=0,
                    timeout=60,
                    _strict_response_validation=True,
                ) as async_sdk:
                    message = await async_sdk.messages.create(
                        model="local-model",
                        max_tokens=1,
                        messages=[{"role": "user", "content": "CONTROL_ASYNC"}],
                    )
                    return message.type == "message" and message.role == "assistant"

            checks = {
                "basic": basic.type == "message" and basic.role == "assistant",
                "system": system.type == "message" and system.role == "assistant",
                "system_blocks": (
                    system_blocks.type == "message"
                    and system_blocks.role == "assistant"
                ),
                "raw_response": (
                    raw.status_code == 200 and raw_message.role == "assistant"
                ),
                "tools_request": tools.role == "assistant",
                "tool_history": tool_history.role == "assistant",
                "count_tokens": count.input_tokens > 0,
                "count_tokens_with_tools": count_tools.input_tokens > count.input_tokens,
                "stream": (
                    streamed.type == "message"
                    and events[0].type == "message_start"
                    and events[-1].type == "message_stop"
                ),
                "async": asyncio.run(async_control()),
            }
            print(
                json.dumps(
                    {
                        "sdk": "1.3.0",
                        "frontend": "python",
                        "checks": checks,
                    },
                    sort_keys=True,
                )
            )
            assert all(checks.values()), checks
            return 0
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
