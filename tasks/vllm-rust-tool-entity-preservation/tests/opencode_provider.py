from __future__ import annotations

import json
import secrets
import threading
import time
import traceback
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


EDIT_ERROR = (
    "Could not find oldString in the file. It must match exactly, "
    "including whitespace, indentation, and line endings."
)
ResponseFactory = Callable[[dict], list[dict]]


def _response_id() -> str:
    return f"chatcmpl-{secrets.token_hex(14)}"


def _tool_call_id() -> str:
    return f"call_{secrets.token_hex(12)}"


def _usage(payload: dict, completion: str) -> dict[str, int]:
    prompt_tokens = max(64, len(json.dumps(payload.get("messages", []))) // 4)
    completion_tokens = max(8, len(completion) // 4)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def text_chunks(payload: dict, content: str) -> list[dict]:
    response_id = _response_id()
    model = payload["model"]
    created = int(time.time())
    return [
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": _usage(payload, content),
        },
    ]


def tool_chunks(payload: dict, name: str, arguments: dict) -> list[dict]:
    response_id = _response_id()
    model = payload["model"]
    created = int(time.time())
    encoded = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
    return [
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": _tool_call_id(),
                                "type": "function",
                                "function": {"name": name, "arguments": encoded},
                            }
                        ],
                    },
                    "finish_reason": None,
                }
            ],
        },
        {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "delta": {}, "finish_reason": "tool_calls"}
            ],
            "usage": _usage(payload, encoded),
        },
    ]


def tool_definitions(payload: dict) -> list[dict]:
    definitions = []
    for item in payload.get("tools", []):
        function = item.get("function", {})
        if not function.get("name"):
            continue
        definitions.append(
            {
                "name": function["name"],
                "description": function.get("description"),
                "parameters": function.get("parameters", {"type": "object"}),
                "strict": function.get("strict"),
            }
        )
    return definitions


def is_title_request(payload: dict) -> bool:
    return any(
        message.get("role") == "system"
        and "title generator" in str(message.get("content"))
        for message in payload.get("messages", [])
    )


class OpenCodeProvider:
    def __init__(self, responder: ResponseFactory) -> None:
        self.responder = responder
        self.requests: list[dict] = []
        self.errors: list[str] = []
        self._lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length", "0"))
                payload = json.loads(self.rfile.read(length))
                try:
                    chunks = provider.respond(payload)
                except Exception as error:
                    provider.errors.append(repr(error))
                    traceback.print_exc()
                    self.send_error(500, "provider response construction failed")
                    return
                body = (
                    "".join(
                        f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                        for item in chunks
                    )
                    + "data: [DONE]\n\n"
                ).encode()
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def __enter__(self) -> OpenCodeProvider:
        self.thread.start()
        return self

    def __exit__(self, *_args) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)
        assert not self.thread.is_alive()

    def respond(self, payload: dict) -> list[dict]:
        with self._lock:
            self.requests.append(payload)
            if is_title_request(payload):
                return text_chunks(payload, "Maven Central query limit")
            return self.responder(payload)
