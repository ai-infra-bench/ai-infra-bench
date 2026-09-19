from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import pytest

MODEL = "local-model"
MODEL_PATH = Path("/opt/models/qwen-template")
SOURCE = Path("/workspace/vllm")
CHAT_PATH = "/v1/chat/completions/derender"
COMPLETION_PATH = "/v1/completions/derender"


@lru_cache(maxsize=1)
def tokenizer():
    from tokenizers import Tokenizer

    return Tokenizer.from_file(str(MODEL_PATH / "tokenizer.json"))


def encode(text: str) -> list[int]:
    return tokenizer().encode(text, add_special_tokens=False).ids


def decode(ids: list[int], *, skip_special: bool = True) -> str:
    return tokenizer().decode(ids, skip_special_tokens=skip_special)


def request_context(**extra: Any) -> dict[str, Any]:
    return {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Explain the result."}],
        "max_tokens": 256,
        **extra,
    }


def tool_definition() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "lookup_city",
            "description": "Look up a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}, "count": {"type": "integer"}},
                "required": ["city"],
            },
        },
    }


def generation(text: str, *, index: int = 0, request_id: str = "generated-request",
               finish_reason: str | None = "stop", **extra: Any) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "choices": [{"index": index, "token_ids": encode(text), "finish_reason": finish_reason}],
        **extra,
    }


class RenderServer:
    """Start the production render-only CLI; no engine or substitute backend."""

    def __init__(self, root: Path, *, tool_parser: str = "none",
                 reasoning_parser: str = "none", thinking: bool = False,
                 frontend: str | None = None) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.log_path = root / "server.log"
        self.log = self.log_path.open("w")
        self.process: subprocess.Popen | None = None
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            self.port = int(listener.getsockname()[1])
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.frontend = frontend or os.environ.get("DERENDER_TEST_FRONTEND", "rust")
        if self.frontend == "rust":
            binary = os.environ.get("DERENDER_RUST_BINARY", str(SOURCE / "rust/target/debug/vllm-rs"))
            args = [binary, "render", str(MODEL_PATH)]
        elif self.frontend == "python":
            args = ["vllm", "launch", "render", str(MODEL_PATH)]
        else:
            raise ValueError(f"unknown frontend {self.frontend}")
        args += [
            "--host", "127.0.0.1", "--port", str(self.port),
            "--served-model-name", MODEL, "--max-model-len", "8192",
            "--max-logprobs", "8",
            "--chat-template", str(MODEL_PATH / "chat_template.jinja"),
            "--default-chat-template-kwargs", json.dumps({"enable_thinking": thinking}),
        ]
        if self.frontend == "rust" or tool_parser != "none":
            args += ["--tool-call-parser", tool_parser]
        if self.frontend == "rust" or reasoning_parser != "none":
            args += ["--reasoning-parser", reasoning_parser]
        if self.frontend == "python" and tool_parser != "none":
            args += ["--enable-auto-tool-choice"]
        environment = os.environ.copy()
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                           VLLM_NO_USAGE_STATS="1", CUDA_VISIBLE_DEVICES="")
        environment.pop("VLLM_USE_RUST_FRONTEND", None)
        if self.frontend == "rust":
            from native_runtime import prepare

            runtime = prepare(root, binary, MODEL_PATH)
            args = [sys.executable, "/tests/native_runtime.py", str(runtime), *args[1:]]
        self.client = httpx.Client(base_url=self.base_url, timeout=30, trust_env=False)
        try:
            self.process = subprocess.Popen(args, cwd=SOURCE, env=environment,
                                            stdout=self.log, stderr=subprocess.STDOUT,
                                            start_new_session=True)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise AssertionError(f"render startup failed:\n{self.log_path.read_text()}")
                try:
                    if self.client.get("/health", timeout=0.5).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            raise AssertionError(f"render startup timed out:\n{self.log_path.read_text()}")
        except BaseException:
            self.close()
            raise

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        assert response.status_code == 200, (path, response.status_code, response.text)
        return response.json()

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        self.client.close()
        self.log.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@pytest.fixture(scope="session")
def plain(tmp_path_factory):
    with RenderServer(tmp_path_factory.mktemp("plain")) as server:
        yield server


@pytest.fixture(scope="session")
def tools_server(tmp_path_factory):
    with RenderServer(tmp_path_factory.mktemp("tools"), tool_parser="hermes") as server:
        yield server


@pytest.fixture(scope="session")
def reasoning_server(tmp_path_factory):
    with RenderServer(tmp_path_factory.mktemp("reasoning"), tool_parser="hermes",
                      reasoning_parser="qwen3", thinking=True) as server:
        yield server
