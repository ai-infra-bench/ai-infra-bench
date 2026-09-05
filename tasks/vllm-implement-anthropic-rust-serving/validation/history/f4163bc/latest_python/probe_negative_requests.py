"""Replay failing request payloads to retain exact HTTP error envelopes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import httpx2

from adapter import PythonServer
from test_rust_request_matrix import INVALID_CASES, MULTIMODAL_CASES, SUCCESS_CASES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="negative-replay-", dir=args.output.parent))
    failed_variants = {
        "tool_result_tool_reference",
        "search_result_input",
        "custom_tool_all_fields",
        "server_tool_use_history",
        "web_search_result_history",
        "web_fetch_and_code_execution_results",
        "bash_and_text_editor_results",
        "tool_search_and_container_upload",
    }
    cases = [
        (
            "test_anthropic_validation_error_envelope",
            {"model": "local-model", "messages": []},
        )
    ]
    cases.extend((f"invalid_request[{name}]", body) for name, body in INVALID_CASES)
    cases.extend(
        (
            f"unsupported_media[{name}]",
            {
                "model": "local-model",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": [block]}],
            },
        )
        for name, block in MULTIMODAL_CASES
    )
    cases.extend(
        (
            f"request_variant[{name}]",
            {
                "model": "local-model",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "MATRIX_BASE_USER"}],
                **body,
            },
        )
        for name, body, _ in SUCCESS_CASES
        if name in failed_variants
    )
    records = []
    with PythonServer(root, ["matrix accepted"]) as server:
        for name, body in cases:
            before = len(server.captures())
            response = httpx2.post(
                server.base_url + "/v1/messages",
                json=body,
                headers={"x-api-key": "matrix-key", "anthropic-version": "2023-06-01"},
                timeout=20,
            )
            captured = server.captures()
            records.append(
                {
                    "case": name,
                    "request": body,
                    "status": response.status_code,
                    "response": response.json(),
                    "generation_submitted": len(captured) > before,
                    "prompt": captured[-1]["prompt"]
                    if len(captured) > before
                    else None,
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
    print(json.dumps({"replayed": len(records)}))


if __name__ == "__main__":
    main()
