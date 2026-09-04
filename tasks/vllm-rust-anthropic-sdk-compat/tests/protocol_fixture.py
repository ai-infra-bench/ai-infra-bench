from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _usage(*, input_tokens: int = 19, output_tokens: int = 7) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": 3,
        "cache_read_input_tokens": 5,
        "cache_creation": {
            "ephemeral_5m_input_tokens": 2,
            "ephemeral_1h_input_tokens": 1,
        },
        "output_tokens_details": {"thinking_tokens": 2},
        "service_tier": "standard",
    }


def _message(body: dict[str, Any], case: str) -> dict[str, Any]:
    content: list[dict[str, Any]]
    stop_reason = "end_turn"
    stop_sequence: str | None = None
    stop_details: dict[str, Any] | None = None
    if case == "parallel_tools":
        content = [
            {"type": "text", "text": "I will check both cities."},
            {
                "type": "tool_use",
                "id": "toolu_weather_paris",
                "name": "get_weather",
                "input": {"city": "Paris", "unit": "c"},
            },
            {
                "type": "tool_use",
                "id": "toolu_weather_tokyo",
                "name": "get_weather",
                "input": {"city": "Tokyo", "unit": "c"},
            },
        ]
        stop_reason = "tool_use"
    elif case == "empty":
        content = [{"type": "text", "text": ""}]
    elif case == "thinking":
        content = [
            {
                "type": "thinking",
                "thinking": "fixture reasoning",
                "signature": "fixture-signature",
            },
            {"type": "text", "text": "fixture answer"},
        ]
    elif case == "redacted":
        content = [
            {"type": "redacted_thinking", "data": "opaque-fixture-data"},
            {"type": "text", "text": "fixture answer"},
        ]
    elif case == "server_tool":
        content = [
            {
                "type": "server_tool_use",
                "id": "srvtoolu_fixture",
                "name": "web_search",
                "input": {"query": "vLLM"},
            }
        ]
        stop_reason = "pause_turn"
    elif case == "stop_sequence":
        content = [{"type": "text", "text": "stopped"}]
        stop_reason = "stop_sequence"
        stop_sequence = "HALT"
    elif case == "max_tokens":
        content = [{"type": "text", "text": "truncated"}]
        stop_reason = "max_tokens"
    elif case == "refusal":
        content = [{"type": "text", "text": ""}]
        stop_reason = "refusal"
        stop_details = {
            "type": "refusal",
            "category": "cyber",
            "explanation": "fixture refusal",
        }
    elif case == "context_limit":
        content = [{"type": "text", "text": "partial"}]
        stop_reason = "model_context_window_exceeded"
    elif case == "parse":
        content = [
            {
                "type": "text",
                "text": '{"city":"Paris","temperature":21}',
            }
        ]
    else:
        content = [{"type": "text", "text": "fixture response"}]
    return {
        "id": f"msg_fixture_{case}",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "local-model"),
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": stop_sequence,
        "stop_details": stop_details,
        "usage": _usage(),
    }


def _event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _stream(body: dict[str, Any], case: str) -> bytes:
    model = body.get("model", "local-model")
    chunks = [
        _event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": f"msg_stream_{case}",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 23,
                        "output_tokens": 0,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "service_tier": "standard",
                    },
                },
            },
        )
    ]
    if case == "stream_parallel_tools":
        for index, tool_id, city in (
            (0, "toolu_stream_paris", "Paris"),
            (1, "toolu_stream_tokyo", "Tokyo"),
        ):
            chunks.extend(
                [
                    _event(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {
                                "type": "tool_use",
                                "id": tool_id,
                                "name": "get_weather",
                                "input": {},
                            },
                        },
                    ),
                    _event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": f'{{"city":"{city}",',
                            },
                        },
                    ),
                    _event(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": '"unit":"c"}',
                            },
                        },
                    ),
                    _event(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": index},
                    ),
                ]
            )
        stop_reason = "tool_use"
        output_tokens = 12
    elif case == "stream_thinking":
        chunks.extend(
            [
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {
                            "type": "thinking",
                            "thinking": "",
                            "signature": "",
                        },
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {
                            "type": "thinking_delta",
                            "thinking": "Check both inputs.",
                        },
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {
                            "type": "signature_delta",
                            "signature": "fixture-signature",
                        },
                    },
                ),
                _event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": 0},
                ),
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 1,
                        "content_block": {"type": "text", "text": ""},
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 1,
                        "delta": {"type": "text_delta", "text": "done"},
                    },
                ),
                _event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": 1},
                ),
            ]
        )
        stop_reason = "end_turn"
        output_tokens = 9
    else:
        chunks.extend(
            [
                _event(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "fixture "},
                    },
                ),
                _event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "stream"},
                    },
                ),
                _event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": 0},
                ),
            ]
        )
        stop_reason = "end_turn"
        output_tokens = 4
    chunks.extend(
        [
            _event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": {
                        "input_tokens": 23,
                        "output_tokens": output_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
                        "output_tokens_details": {
                            "thinking_tokens": 3 if case == "stream_thinking" else 0
                        },
                    },
                },
            ),
            _event("message_stop", {"type": "message_stop"}),
        ]
    )
    return "".join(chunks).encode()


class FixtureServer(AbstractContextManager["FixtureServer"]):
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args: Any) -> None:
                return

            def _send(self, status: int, payload: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(len(payload)))
                self.send_header("request-id", "req_fixture_123")
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length", "0"))
                raw = self.rfile.read(length)
                body = json.loads(raw or b"{}")
                case = self.headers.get("x-ai-infra-case", "text")
                outer.records.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": {key.lower(): value for key, value in self.headers.items()},
                        "body": body,
                        "case": case,
                    }
                )
                if self.path == "/v1/messages/count_tokens":
                    self._send(
                        200,
                        json.dumps({"input_tokens": 37}).encode(),
                        "application/json",
                    )
                    return
                if self.path != "/v1/messages":
                    self._send(
                        404,
                        b'{"type":"error","error":{"type":"not_found_error","message":"Not Found"}}',
                        "application/json",
                    )
                    return
                if case == "error":
                    self._send(
                        400,
                        b'{"type":"error","error":{"type":"invalid_request_error","message":"fixture rejected request"}}',
                        "application/json",
                    )
                    return
                if body.get("stream"):
                    self._send(200, _stream(body, case), "text/event-stream")
                    return
                self._send(
                    200,
                    json.dumps(_message(body, case)).encode(),
                    "application/json",
                )

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"

    def __enter__(self) -> "FixtureServer":
        self._thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
