"""Disambiguate selected failures without editing scored test assertions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

import anthropic
import httpx2

from adapter import PythonServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="detail-cases-", dir=args.output.parent))
    original_popen = subprocess.Popen
    records = []

    for name, enabled, output in [
        (
            "original_thinking_disabled",
            False,
            "<think>reasoning sentinel</think>answer sentinel",
        ),
        (
            "thinking_enabled_same_script",
            True,
            "<think>reasoning sentinel</think>answer sentinel",
        ),
        (
            "thinking_enabled_continuation",
            True,
            "reasoning sentinel</think>answer sentinel",
        ),
    ]:

        def configured_popen(command, *positional, **kwargs):
            command = list(command)
            command[command.index("--default-chat-template-kwargs") + 1] = json.dumps(
                {"enable_thinking": enabled, "preserve_thinking": True}
            )
            return original_popen(command, *positional, **kwargs)

        with patch("adapter.subprocess.Popen", side_effect=configured_popen):
            with PythonServer(
                root / name,
                [output],
                reasoning_parser="qwen3",
                chunk_sizes=[1, 2, 5, 3],
            ) as server:
                client = anthropic.Anthropic(
                    api_key="probe",
                    base_url=server.base_url,
                    max_retries=0,
                    _strict_response_validation=True,
                )
                payload = dict(
                    model="local-model",
                    max_tokens=2048,
                    thinking={"type": "enabled", "budget_tokens": 1024},
                    messages=[{"role": "user", "content": "SDK_MATRIX_HELLO"}],
                )
                row = {
                    "case": name,
                    "enable_thinking": enabled,
                    "model_output": output,
                }
                try:
                    with client.messages.stream(**payload) as stream:
                        final = stream.get_final_message()
                    row["content"] = [block.model_dump() for block in final.content]
                except anthropic.APIResponseValidationError as error:
                    row["exception"] = type(error).__name__
                    row["invalid_event"] = error.body
                raw = httpx2.post(
                    server.base_url + "/v1/messages",
                    json={**payload, "stream": True},
                    timeout=20,
                )
                row["raw_sse"] = raw.text
                row.update(
                    {
                        "rendered_template_kwargs": server.render_captures()[-1][
                            "template_kwargs"
                        ],
                        "converted_thinking_token_budget": server.render_captures()[-1][
                            "chat_request"
                        ]["thinking_token_budget"],
                    }
                )
                records.append(row)

    with PythonServer(
        root / "authentication", ["authenticated"], api_key="secret-key"
    ) as server:
        payload = {
            "model": "local-model",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "authentication probe"}],
        }
        for name, headers in [
            ("correct_x_api_key", {"x-api-key": "secret-key"}),
            ("correct_bearer", {"authorization": "Bearer secret-key"}),
            ("wrong_x_api_key", {"x-api-key": "wrong-key"}),
        ]:
            response = httpx2.post(
                server.base_url + "/v1/messages",
                headers=headers,
                json=payload,
                timeout=20,
            )
            records.append(
                {"case": name, "status": response.status_code, "body": response.json()}
            )

    with PythonServer(root / "stream_error", [""], finish_reason="error") as server:
        response = httpx2.post(
            server.base_url + "/v1/messages",
            json={
                "model": "local-model",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": "error probe"}],
            },
            timeout=20,
        )
        records.append(
            {
                "case": "raw_stream_engine_error",
                "status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body": response.text,
            }
        )

    args.output.write_text(
        json.dumps(
            {
                "source_commit": "e962733e08d10f7ca65dac4df99e116460b8b174",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    for record in records:
        print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
