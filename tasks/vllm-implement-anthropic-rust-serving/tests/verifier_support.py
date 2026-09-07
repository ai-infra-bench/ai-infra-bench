from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Any


class RustServer:
    def __init__(
        self,
        root: Path,
        outputs: list[str],
        *,
        model: str = "local-model",
        chunk_sizes: list[int] | None = None,
        tool_parser: str = "qwen3_coder",
        reasoning_parser: str = "none",
        finish_reason: str = "stop",
        stop_text: str | None = None,
        api_key: str | None = None,
        cached_tokens: int = 0,
        enable_thinking: bool = False,
    ) -> None:
        self.stop_file = root / "stop-rust-server"
        self.capture_file = root / "engine-capture.jsonl"
        self.render_capture_file = root / "renderer-capture.jsonl"
        environment = os.environ.copy()
        environment.update(
            {
                "AI_INFRA_SERVER_MODEL": model,
                "AI_INFRA_SERVER_OUTPUTS_JSON": json.dumps(outputs),
                "AI_INFRA_SERVER_CHUNK_SIZES_JSON": json.dumps(chunk_sizes or []),
                "AI_INFRA_SERVER_TOOL_PARSER": tool_parser,
                "AI_INFRA_SERVER_REASONING_PARSER": reasoning_parser,
                "AI_INFRA_SERVER_FINISH_REASON": finish_reason,
                "AI_INFRA_SERVER_CAPTURE_FILE": str(self.capture_file),
                "AI_INFRA_SERVER_RENDER_CAPTURE_FILE": str(self.render_capture_file),
                "AI_INFRA_SERVER_STOP_FILE": str(self.stop_file),
                "AI_INFRA_SERVER_CACHED_TOKENS": str(cached_tokens),
                "AI_INFRA_SERVER_ENABLE_THINKING": str(enable_thinking).lower(),
            }
        )
        if stop_text is not None:
            environment["AI_INFRA_SERVER_STOP_TEXT"] = stop_text
        if api_key is not None:
            environment["AI_INFRA_SERVER_API_KEY"] = api_key
        self.process = subprocess.Popen(
            [
                "cargo",
                "test",
                "--quiet",
                "--manifest-path",
                "rust/Cargo.toml",
                "-p",
                "vllm-server",
                "ai_infra_anthropic_http_server",
                "--",
                "--nocapture",
                "--test-threads=1",
            ],
            cwd="/workspace/vllm",
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=True,
        )
        self.output: list[str] = []
        self.base_url = self._read_address()

    def _read_address(self) -> str:
        assert self.process.stdout is not None
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                remainder = self.process.stdout.read()
                if remainder:
                    self.output.append(remainder)
                raise AssertionError(
                    f"Rust server exited before startup: {''.join(self.output)}"
                )
            readable, _, _ = select.select([self.process.stdout], [], [], 1)
            if not readable:
                continue
            line = self.process.stdout.readline()
            if not line:
                continue
            self.output.append(line)
            marker = "AI_INFRA_VLLM_SERVER="
            if marker in line:
                return line.split(marker, 1)[1].strip()
        raise AssertionError(f"timed out starting Rust server: {''.join(self.output)}")

    def captures(self) -> list[dict[str, Any]]:
        if not self.capture_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.capture_file.read_text().splitlines()
            if line.strip()
        ]

    def render_captures(self) -> list[dict[str, Any]]:
        if not self.render_capture_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.render_capture_file.read_text().splitlines()
            if line.strip()
        ]

    def __enter__(self) -> "RustServer":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.stop_file.touch()
        try:
            stdout, _ = self.process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            stdout, _ = self.process.communicate(timeout=10)
        if stdout:
            self.output.append(stdout)
        assert self.process.returncode == 0, "".join(self.output)


def temporary_root(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix)


def message_text(message: Any) -> str:
    """Compare generated text without prescribing protocol block segmentation."""
    assert all(block.type == "text" for block in message.content)
    return "".join(block.text for block in message.content)


@lru_cache(maxsize=1)
def reference_tokenizer():
    # Independent HF tokenizers implementation; Rust uses fastokens on the same
    # immutable vocabulary. No model tensors or network are involved.
    from tokenizers import Tokenizer

    return Tokenizer.from_file("/opt/models/qwen-template/tokenizer.json")


def assert_engine_token_ids(capture: dict[str, Any]) -> None:
    expected = (
        reference_tokenizer().encode(capture["prompt"], add_special_tokens=False).ids
    )
    assert capture["prompt_token_ids"] == expected


def assert_count_matches_generation(sdk, server: RustServer, **kwargs: Any) -> int:
    before = len(server.captures())
    count = sdk.messages.count_tokens(**kwargs).input_tokens
    assert len(server.captures()) == before, "count_tokens submitted generation"
    assert count > 0
    # Repeated requests may legitimately reuse cached tokenization.
    assert sdk.messages.count_tokens(**kwargs).input_tokens == count
    assert len(server.captures()) == before
    sdk.messages.create(**kwargs, max_tokens=64)
    capture = server.captures()[-1]
    assert_engine_token_ids(capture)
    assert count == len(capture["prompt_token_ids"])
    return count


def assert_json_constraint(capture: dict[str, Any], schema: dict[str, Any]) -> None:
    import llguidance
    from vllm.sampling_params import StructuredOutputsParams
    from vllm.v1.structured_output.backend_guidance import serialize_guidance_grammar
    from vllm.v1.structured_output.request import get_structured_output_key

    structured = capture["sampling_params"].get("structured_outputs")
    assert structured, "JSON schema never reached the engine"
    params = StructuredOutputsParams(
        **{key: value for key, value in structured.items() if not key.startswith("_")}
    )
    kind, specification = get_structured_output_key(params)
    grammar = serialize_guidance_grammar(
        kind,
        specification,
        params.disable_any_whitespace,
        params.disable_additional_properties,
    )
    # Execute the pinned engine's grammar compiler/matcher. Equivalent JSON,
    # regex, or grammar representations may pass; field names/schema layout
    # chosen by a candidate are not the correctness criterion.
    valid = {
        key: 21 if value["type"] == "integer" else "Paris 世界"
        for key, value in schema["properties"].items()
    }
    probes = [
        (valid, True),
        (
            {
                **valid,
                **{
                    key: -7 if value["type"] == "integer" else "Oslo"
                    for key, value in schema["properties"].items()
                },
            },
            True,
        ),
    ]
    for key, value in schema["properties"].items():
        probes.append(
            ({**valid, key: "wrong-type" if value["type"] == "integer" else 7}, False)
        )
    for key in schema.get("required", []):
        probes.append(
            ({name: value for name, value in valid.items() if name != key}, False)
        )
    if schema.get("additionalProperties") is False:
        probes.append(({**valid, "unexpected_property": True}, False))
    for value, expected in probes:
        matcher = llguidance.LLMatcher(guidance_tokenizer(), grammar)
        assert not matcher.get_error(), matcher.get_error()
        ids = (
            reference_tokenizer()
            .encode(json.dumps(value, ensure_ascii=False), add_special_tokens=False)
            .ids
        )
        accepted = matcher.consume_tokens(ids) and matcher.is_accepting()
        assert accepted is expected, {
            "value": value,
            "expected": expected,
            "structured_outputs": structured,
        }


@lru_cache(maxsize=1)
def guidance_tokenizer():
    from llguidance.hf import from_tokenizer
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        "/opt/models/qwen-template", local_files_only=True
    )
    return from_tokenizer(tokenizer, len(tokenizer))


def minimax_tool_call(name: str, arguments: list[tuple[str, str]]) -> str:
    params = "".join(
        f'<parameter name="{key}">{value}</parameter>' for key, value in arguments
    )
    return f'<minimax:tool_call><invoke name="{name}">{params}</invoke></minimax:tool_call>'


def minimax_parallel_tool_calls(cities: list[str]) -> str:
    invokes = "".join(
        '<invoke name="get_weather">'
        f'<parameter name="city">{city}</parameter>'
        '<parameter name="unit">c</parameter>'
        "</invoke>"
        for city in cities
    )
    return f"<minimax:tool_call>{invokes}</minimax:tool_call>"
