"""Measure the pinned Python adapter against the request-side Rust cases.

This audit is diagnostic, not an Oracle. It uses real Python HTTP, rendering,
tokenization, and CPU dummy-weight generation. Output-state-machine cases that
require scripted generation are explicitly listed as not measured here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic
import httpx2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from python_frontend_control import free_port, wait_ready, write_model
from test_rust_request_matrix import (
    SUCCESS_CASES,
    COUNT_CASES,
    INVALID_CASES,
    MULTIMODAL_CASES,
)
from verifier_support import reference_tokenizer


def read_captures(path: Path) -> list[dict]:
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


def token_ids(prompt: dict) -> list[int]:
    if "prompt_token_ids" in prompt:
        return prompt["prompt_token_ids"]
    if "decoder_prompt" in prompt:
        return token_ids(prompt["decoder_prompt"])
    raise AssertionError(f"Unrecognized Python engine input: {list(prompt)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records: list[dict] = []

    def record(case: str, boundary: str, operation):
        row = {"case": case, "boundary": boundary}
        try:
            row.update(operation() or {})
            row["status"] = "passed"
        except Exception as error:
            row["status"] = "incompatible"
            row["exception"] = type(error).__name__
            row["detail"] = str(error)[:3000]
            if isinstance(error, anthropic.APIStatusError):
                row["http_status"] = error.status_code
                row["body"] = error.body
        records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    with tempfile.TemporaryDirectory(prefix="python-compat-audit-") as raw:
        root = Path(raw)
        model = root / "model"
        write_model(model)
        config = json.loads((model / "config.json").read_text())
        config["max_position_embeddings"] = 4096
        (model / "config.json").write_text(json.dumps(config))
        capture_path = root / "engine.jsonl"
        log_path = root / "server.log"
        port = free_port()
        environment = os.environ.copy()
        environment.pop("VLLM_USE_RUST_FRONTEND", None)
        environment.update(
            {
                "GLOO_SOCKET_IFNAME": "lo",
                "VLLM_CPU_KVCACHE_SPACE": "1",
                "VLLM_HOST_IP": "127.0.0.1",
                "PYTHON_COMPAT_CAPTURE": str(capture_path),
            }
        )
        command = [
            sys.executable,
            str(Path(__file__).with_name("python_frontend_capture.py")),
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
            "--default-chat-template-kwargs",
            '{"enable_thinking":false,"preserve_thinking":true}',
            "--enable-auto-tool-choice",
            "--tool-call-parser",
            "qwen3_coder",
            "--enable-prompt-tokens-details",
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
        with log_path.open("w") as log:
            process = subprocess.Popen(
                command,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )
        try:
            wait_ready(port, process, log_path)
            base_url = f"http://127.0.0.1:{port}"
            sdk = anthropic.Anthropic(
                api_key="audit-key",
                base_url=base_url,
                max_retries=0,
                timeout=60,
                _strict_response_validation=True,
            )

            for name, overrides, sentinels in SUCCESS_CASES:

                def probe(overrides=overrides, sentinels=sentinels, name=name):
                    before = len(read_captures(capture_path))
                    kwargs = {
                        "model": "local-model",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "MATRIX_BASE_USER"}],
                        **overrides,
                    }
                    message = sdk.messages.create(**kwargs)
                    assert message.role == "assistant"
                    captures = read_captures(capture_path)
                    assert len(captures) == before + 1
                    capture = captures[-1]
                    ids = token_ids(capture["prompt"])
                    prompt = reference_tokenizer().decode(
                        ids, skip_special_tokens=False
                    )
                    missing = [text for text in sentinels if text not in prompt]
                    assert not missing, (
                        f"Content missing from real rendered prompt: {missing}"
                    )
                    if name == "json_schema_output":
                        structured = capture["sampling_params"].get(
                            "structured_outputs"
                        )
                        assert structured and structured.get("json"), (
                            "Requested JSON schema was not forwarded"
                        )
                    if name == "adaptive_thinking_output_effort":
                        # The native Rust contract checks this semantic option;
                        # inspect Python's production conversion as a separate
                        # component observation, not a rendered-text guess.
                        from vllm.entrypoints.anthropic.protocol import (
                            AnthropicMessagesRequest,
                        )
                        from vllm.entrypoints.anthropic.serving import (
                            AnthropicServingMessages,
                        )

                        converted = AnthropicServingMessages._convert_anthropic_to_openai_request(
                            AnthropicMessagesRequest(**kwargs)
                        )
                        assert converted.reasoning_effort == "high"
                    return {
                        "http_status": 200,
                        "prompt_tokens": len(ids),
                        "scope": "request acceptance, rendered content, and explicit semantic assertions; generated text is not compared",
                    }

                record(
                    f"test_request_variant_reaches_rust_semantic_path[{name}]",
                    "real Python HTTP + renderer + tokenizer + engine input",
                    probe,
                )

            for name, extra in COUNT_CASES:

                def probe(name=name, extra=extra):
                    kwargs = {
                        "model": "local-model",
                        "messages": [{"role": "user", "content": f"COUNT_{name}"}],
                        **extra,
                    }
                    before = len(read_captures(capture_path))
                    count = sdk.messages.count_tokens(**kwargs).input_tokens
                    assert len(read_captures(capture_path)) == before
                    assert sdk.messages.count_tokens(**kwargs).input_tokens == count
                    sdk.messages.create(**kwargs, max_tokens=1)
                    actual = len(token_ids(read_captures(capture_path)[-1]["prompt"]))
                    assert count == actual, (
                        f"count_tokens={count}, generated request prompt tokens={actual}"
                    )
                    return {"input_tokens": count, "generation_prompt_tokens": actual}

                record(
                    f"test_count_tokens_request_variants[{name}]",
                    "real Python HTTP; count versus actual generation input",
                    probe,
                )

            for name, body in INVALID_CASES:

                def probe(body=body):
                    response = httpx2.post(
                        base_url + "/v1/messages", json=body, timeout=60
                    )
                    payload = response.json()
                    assert response.status_code == 400, (
                        f"status={response.status_code}, body={payload}"
                    )
                    assert (
                        payload.get("type") == "error"
                        and payload["error"]["type"] == "invalid_request_error"
                    ), payload
                    return {"http_status": response.status_code}

                record(
                    f"test_invalid_request_returns_anthropic_error[{name}]",
                    "real Python HTTP error envelope",
                    probe,
                )

            for name, block in MULTIMODAL_CASES:

                def probe(block=block):
                    try:
                        sdk.messages.create(
                            model="local-model",
                            max_tokens=1,
                            messages=[{"role": "user", "content": [block]}],
                        )
                    except anthropic.BadRequestError as error:
                        assert error.body["error"]["type"] == "invalid_request_error", (
                            error.body
                        )
                        return {"http_status": error.status_code}
                    raise AssertionError(
                        "Expected Anthropic BadRequestError for unsupported media"
                    )

                record(
                    f"test_unsupported_backend_media_fails_cleanly[{name}]",
                    "real Python HTTP, text-only CPU model; no media-support claim",
                    probe,
                )

            basic = {
                "model": "local-model",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "CLIENT_MODE_AUDIT"}],
            }

            def access_modes():
                assert sdk.messages.create(**basic).role == "assistant"
                raw = sdk.messages.with_raw_response.create(**basic)
                assert raw.status_code == 200 and raw.parse().role == "assistant"
                with sdk.messages.with_streaming_response.create(**basic) as response:
                    assert response.parse().role == "assistant"
                return {"modes": ["sync", "raw", "streaming_response"]}

            record(
                "sync_access_modes",
                "real Python HTTP, SDK type validation",
                access_modes,
            )

            def stream_mode():
                with sdk.messages.stream(**basic) as stream:
                    events = list(stream)
                    message = stream.get_final_message()
                assert (
                    events[0].type == "message_start"
                    and events[-1].type == "message_stop"
                )
                assert message.role == "assistant"
                return {"event_types": [event.type for event in events]}

            record(
                "text_stream_lifecycle",
                "real Python HTTP/SSE, SDK accumulation",
                stream_mode,
            )

            def async_mode():
                async def run():
                    async with anthropic.AsyncAnthropic(
                        api_key="audit-key",
                        base_url=base_url,
                        max_retries=0,
                        timeout=60,
                        _strict_response_validation=True,
                    ) as client:
                        assert (
                            await client.messages.create(**basic)
                        ).role == "assistant"

                asyncio.run(run())

            record("async_access", "real Python HTTP, SDK type validation", async_mode)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.with_suffix(".server.log").write_text(log_path.read_text())
            args.output.with_suffix(".engine.jsonl").write_text(
                capture_path.read_text() if capture_path.exists() else ""
            )

    result = {
        "base_commit": "e196268bade5291c3fd80906bf9cd8c64851b21b",
        "sdk": "anthropic==1.3.0",
        "records": records,
        "summary": {
            status: sum(row["status"] == status for row in records)
            for status in ("passed", "incompatible")
        },
        "not_measured": [
            "deterministic parallel-tool/JSON-fragmentation output",
            "scripted reasoning and empty-output cases",
            "engine error/stop injection",
            "authentication configured with an API key",
            "concurrent scripted output identity",
            "SDK fixture-only response unions and all HTTP status mappings",
        ],
        "limitation": "These are Python equivalents of request-side assertions, not a run of the complete Rust verifier or a full positive implementation. An accepted unknown field is not evidence that its semantics are implemented. No SDK feature introduction date is inferred from a Python failure.",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result["summary"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
