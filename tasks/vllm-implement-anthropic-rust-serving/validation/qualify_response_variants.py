"""Qualify the scored stream predicate on equivalent SDK-valid encodings.

This is a verifier-only protocol control, not a candidate Rust implementation.
Run with PYTHONPATH pointing at the task tests and anthropic==1.3.0 installed.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

import test_rust_sdk_matrix as target


class ProtocolServer:
    split_blocks = False
    intermediate_usage = False

    def __init__(self, root, outputs, *, cached_tokens=0, **kwargs):
        output = outputs[0]
        texts = [output[:4], output[4:]] if self.split_blocks else [output]
        events = []

        def emit(kind, **fields):
            events.append(
                f"event: {kind}\ndata: {json.dumps({'type': kind, **fields})}\n\n"
            )

        emit(
            "message_start",
            message={
                "id": "msg_protocol_alternative",
                "type": "message",
                "role": "assistant",
                "model": "local-model",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 19,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": cached_tokens,
                },
            },
        )
        for index, text in enumerate(texts):
            emit(
                "content_block_start",
                index=index,
                content_block={"type": "text", "text": ""},
            )
            emit(
                "content_block_delta",
                index=index,
                delta={"type": "text_delta", "text": text},
            )
            emit("content_block_stop", index=index)
        if self.intermediate_usage:
            emit(
                "message_delta",
                delta={"stop_reason": None, "stop_sequence": None},
                usage={"output_tokens": 1},
            )
        emit(
            "message_delta",
            delta={"stop_reason": "end_turn", "stop_sequence": None},
            usage={"output_tokens": 3},
        )
        emit("message_stop")
        payload = "".join(events).encode()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                request = json.loads(
                    self.rfile.read(int(self.headers["content-length"]))
                )
                assert self.path == "/v1/messages" and request["stream"] is True
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self.http.server_port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()


def main():
    original = target.RustServer
    results = []
    try:
        target.RustServer = ProtocolServer
        for split_blocks in (False, True):
            for intermediate_usage in (False, True):
                ProtocolServer.split_blocks = split_blocks
                ProtocolServer.intermediate_usage = intermediate_usage
                target.test_stream_helper_event_order_and_accumulation(Path("/tmp"))
                results.append(
                    {
                        "split_blocks": split_blocks,
                        "intermediate_usage": intermediate_usage,
                        "passed": True,
                    }
                )
    finally:
        target.RustServer = original
    print(
        json.dumps(
            {
                "scope": "SDK stream predicate only; no complete Rust alternative",
                "cases": results,
            }
        )
    )


if __name__ == "__main__":
    main()
