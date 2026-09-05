from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


ERROR_CASES: dict[str, tuple[int, str, str]] = {
    "error_400": (400, "invalid_request_error", "fixture rejected request"),
    "error_401": (401, "authentication_error", "fixture authentication failed"),
    "error_403": (403, "permission_error", "fixture permission denied"),
    "error_404": (404, "not_found_error", "fixture model not found"),
    "error_409": (409, "invalid_request_error", "fixture conflict"),
    "error_413": (413, "request_too_large", "fixture request too large"),
    "error_422": (422, "invalid_request_error", "fixture request unprocessable"),
    "error_429": (429, "rate_limit_error", "fixture rate limited"),
    "error_500": (500, "api_error", "fixture internal error"),
    "error_529": (529, "overloaded_error", "fixture overloaded"),
}


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
    elif case == "citations":
        content = [
            {
                "type": "text",
                "text": "Cited fixture text",
                "citations": [
                    {
                        "type": "char_location",
                        "cited_text": "fixture",
                        "document_index": 0,
                        "document_title": "Fixture document",
                        "start_char_index": 6,
                        "end_char_index": 13,
                    }
                ],
            }
        ]
    elif case == "hosted_web":
        content = [
            {
                "type": "server_tool_use",
                "id": "srvtoolu_search_fixture",
                "name": "web_search",
                "input": {"query": "vLLM"},
                "caller": {"type": "direct"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_search_fixture",
                "caller": {"type": "direct"},
                "content": [
                    {
                        "type": "web_search_result",
                        "url": "https://example.invalid/vllm",
                        "title": "vLLM fixture result",
                        "encrypted_content": "encrypted-search-fixture",
                        "page_age": "1 day",
                    }
                ],
            },
            {
                "type": "web_fetch_tool_result",
                "tool_use_id": "srvtoolu_fetch_fixture",
                "caller": {"type": "direct"},
                "content": {
                    "type": "web_fetch_result",
                    "url": "https://example.invalid/document",
                    "retrieved_at": "2026-09-01T00:00:00Z",
                    "content": {
                        "type": "document",
                        "title": "Fetched fixture",
                        "source": {
                            "type": "text",
                            "media_type": "text/plain",
                            "data": "fetched fixture body",
                        },
                    },
                },
            },
        ]
    elif case == "hosted_code":
        content = [
            {
                "type": "code_execution_tool_result",
                "tool_use_id": "srvtoolu_code_fixture",
                "content": {
                    "type": "code_execution_result",
                    "return_code": 0,
                    "stdout": "code fixture output",
                    "stderr": "",
                    "content": [
                        {
                            "type": "code_execution_output",
                            "file_id": "file_code_fixture",
                        }
                    ],
                },
            },
            {
                "type": "bash_code_execution_tool_result",
                "tool_use_id": "srvtoolu_bash_fixture",
                "content": {
                    "type": "bash_code_execution_result",
                    "return_code": 0,
                    "stdout": "bash fixture output",
                    "stderr": "",
                    "content": [
                        {
                            "type": "bash_code_execution_output",
                            "file_id": "file_bash_fixture",
                        }
                    ],
                },
            },
            {
                "type": "text_editor_code_execution_tool_result",
                "tool_use_id": "srvtoolu_editor_fixture",
                "content": {
                    "type": "text_editor_code_execution_view_result",
                    "file_type": "text",
                    "content": "editor fixture output",
                    "start_line": 1,
                    "num_lines": 1,
                    "total_lines": 1,
                },
            },
        ]
    elif case == "tool_search_upload":
        content = [
            {
                "type": "tool_search_tool_result",
                "tool_use_id": "srvtoolu_tool_search_fixture",
                "content": {
                    "type": "tool_search_tool_search_result",
                    "tool_references": [
                        {"type": "tool_reference", "tool_name": "get_weather"}
                    ],
                },
            },
            {"type": "container_upload", "file_id": "file_upload_fixture"},
        ]
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
    if case == "stream_error":
        chunks.append(
            _event(
                "error",
                {
                    "type": "error",
                    "error": {
                        "type": "overloaded_error",
                        "message": "fixture stream overloaded",
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
