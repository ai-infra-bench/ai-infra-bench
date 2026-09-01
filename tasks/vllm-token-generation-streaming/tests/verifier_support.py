from __future__ import annotations

import json
from collections.abc import Iterable

import httpx


def request_body(
    first_token: int = 128000,
    *,
    stream: bool = True,
    sampling: dict | None = None,
    stream_options: dict | None = None,
) -> dict:
    body = {
        "request_id": f"hidden-{first_token}",
        "token_ids": [first_token, 12, 13, 14],
        "sampling_params": sampling or {"max_tokens": 8},
        "stream": stream,
    }
    if stream_options is not None:
        body["stream_options"] = stream_options
    return body


def stream_request(url: str, body: dict) -> tuple[httpx.Response, list[str]]:
    with httpx.stream("POST", url, json=body, timeout=15) as response:
        lines = [line for line in response.iter_lines() if line]
    return response, lines


def parse_sse(lines: Iterable[str]) -> list[dict | str]:
    parsed: list[dict | str] = []
    for line in lines:
        assert line.startswith("data: "), line
        payload = line.removeprefix("data: ")
        parsed.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return parsed


def data_chunks(parsed: list[dict | str]) -> list[dict]:
    return [item for item in parsed if isinstance(item, dict)]
