"""Python server adapter for the existing Rust-authored behavior tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import httpx2

from python_frontend_control import free_port, write_model


class PythonServer:
    def __init__(
        self,
        root: Path,
        outputs: list[str],
        *,
        model="local-model",
        chunk_sizes=None,
        tool_parser="qwen3_coder",
        reasoning_parser="none",
        finish_reason="stop",
        stop_text=None,
        api_key=None,
        cached_tokens=0,
    ):
        root.mkdir(parents=True, exist_ok=True)
        self.capture_file = root / "engine-capture.jsonl"
        self.render_capture_file = root / "renderer-capture.jsonl"
        self.log_path = root / "python-server.log"
        model_path = root / "model"
        write_model(model_path)
        config = json.loads((model_path / "config.json").read_text())
        config["max_position_embeddings"] = 4096
        (model_path / "config.json").write_text(json.dumps(config))
        port = free_port()
        self.base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.pop("VLLM_USE_RUST_FRONTEND", None)
        environment.update(
            {
                "GLOO_SOCKET_IFNAME": "lo",
                "VLLM_CPU_KVCACHE_SPACE": "1",
                "VLLM_HOST_IP": "127.0.0.1",
                "AI_INFRA_SERVER_OUTPUTS_JSON": json.dumps(outputs),
                "AI_INFRA_SERVER_CHUNK_SIZES_JSON": json.dumps(chunk_sizes or []),
                "AI_INFRA_SERVER_CAPTURE_FILE": str(self.capture_file),
                "AI_INFRA_SERVER_RENDER_CAPTURE_FILE": str(self.render_capture_file),
                "AI_INFRA_SERVER_CACHED_TOKENS": str(cached_tokens),
                "AI_INFRA_SERVER_FINISH_REASON": finish_reason,
            }
        )
        if stop_text is not None:
            environment["AI_INFRA_SERVER_STOP_TEXT"] = stop_text
        command = [
            sys.executable,
            str(Path(__file__).with_name("server.py")),
            "serve",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--served-model-name",
            model,
            "--tokenizer",
            "/opt/models/qwen-template",
            "--chat-template",
            "/opt/models/qwen-template/chat_template.jinja",
            "--default-chat-template-kwargs",
            '{"enable_thinking":false,"preserve_thinking":true}',
            "--enable-prompt-tokens-details",
            "--disable-log-stats",
            "--load-format",
            "dummy",
            "--dtype",
            "float32",
            "--max-model-len",
            "4096",
            "--max-num-batched-tokens",
            "4096",
            "--max-num-seqs",
            "8",
            "--enforce-eager",
        ]
        if tool_parser != "none":
            command.extend(
                ["--enable-auto-tool-choice", "--tool-call-parser", tool_parser]
            )
        if reasoning_parser != "none":
            command.extend(["--reasoning-parser", reasoning_parser])
        if api_key is not None:
            command.extend(["--api-key", api_key])
        with self.log_path.open("w") as log:
            self.process = subprocess.Popen(
                command,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        self.output = []
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise AssertionError(self.log_path.read_text())
                try:
                    if (
                        httpx2.get(self.base_url + "/health", timeout=1).status_code
                        == 200
                    ):
                        return
                except httpx2.HTTPError:
                    pass
                time.sleep(0.25)
            raise AssertionError(
                "Python reference startup timed out:\n" + self.log_path.read_text()
            )
        except BaseException:
            self.close()
            raise

    def captures(self):
        return self._read(self.capture_file)

    def render_captures(self):
        return self._read(self.render_capture_file)

    @staticmethod
    def _read(path):
        return (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )

    def __enter__(self):
        return self

    def close(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        self.output = [self.log_path.read_text()]

    def __exit__(self, *args):
        exited = self.process.poll()
        self.close()
        assert exited in (None, 0), "Python server exited unexpectedly:\n" + self.output[0]
