from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


ERROR_CASES: dict[str, tuple[int, str, str]] = {
    "error_400": (400, "invalid_request_error", "fixture rejected request"),
    "error_401": (401, "authentication_error", "fixture authentication failed"),
    "error_404": (404, "not_found_error", "fixture model not found"),
    "error_500": (500, "api_error", "fixture internal error"),
}


def _usage(*, input_tokens: int = 19, output_tokens: int = 7) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": 3,
        "cache_read_input_tokens": 5,
    }


def _message(body: dict[str, Any], case: str) -> dict[str, Any]:
    content: list[dict[str, Any]]
    stop_reason = "end_turn"
    stop_sequence: str | None = None
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
    elif case == "stop_sequence":
        content = [{"type": "text", "text": "stopped"}]
        stop_reason = "stop_sequence"
        stop_sequence = "HALT"
    elif case == "max_tokens":
        content = [{"type": "text", "text": "truncated"}]
        stop_reason = "max_tokens"
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
                    },
                },
            },
        )
    ]
    if case == "stream_error":
        chunks.append(
            _event(
                "error",
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": "fixture stream failed",
                    },
                },
            )
        )
        return "".join(chunks).encode()
    if case == "stream_ping":
        chunks.append(_event("ping", {"type": "ping"}))

    stop_sequence: str | None = None
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
    elif case == "stream_unicode_tool":
        tool_input = json.dumps(
            {
                "city": "München",
                "note": 'quote " slash \\ emoji 🍣',
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        quote_escape = tool_input.index('\\"') + 1
        slash_escape = tool_input.index("\\\\") + 1
        split_points = sorted({1, 9, quote_escape, slash_escape, len(tool_input) - 1})
        fragments: list[str] = []
        start = 0
        for end in split_points:
            fragments.append(tool_input[start:end])
            start = end
        fragments.append(tool_input[start:])
        chunks.append(
            _event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {
                        "type": "tool_use",
                        "id": "toolu_unicode_fixture",
                        "name": "get_weather",
                        "input": {},
                    },
                },
            )
        )
        chunks.extend(
            _event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": fragment,
                    },
                },
            )
            for fragment in fragments
        )
        chunks.append(
            _event(
                "content_block_stop",
                {"type": "content_block_stop", "index": 0},
            )
        )
        stop_reason = "tool_use"
        output_tokens = 17
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
        if case == "stream_stop_sequence":
            stop_reason = "stop_sequence"
            stop_sequence = "HALT"
        elif case == "stream_max_tokens":
            stop_reason = "max_tokens"
        else:
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
                        "stop_sequence": stop_sequence,
                    },
                    "usage": {
                        "input_tokens": 23,
                        "output_tokens": output_tokens,
                        "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 0,
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
                        "headers": {
                            key.lower(): value for key, value in self.headers.items()
                        },
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
                if case in ERROR_CASES:
                    status, error_type, message = ERROR_CASES[case]
                    self._send(
                        status,
                        json.dumps(
                            {
                                "type": "error",
                                "error": {"type": error_type, "message": message},
                            }
                        ).encode(),
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
