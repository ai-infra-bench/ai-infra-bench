#!/usr/bin/env python3
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from transformers import AutoTokenizer

from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.parser.abstract_parser import Parser
from vllm.parser.parser_manager import ParserManager


MODEL_PATH = "/opt/models/minimax-m3"
NS = "]<]minimax[>["
REASONING = "I should search the current checkout incident runbook first."
TOOL_TEXT = (
    f"{NS}<tool_call>\n"
    f'{NS}<invoke name="search_incident_runbooks">'
    f"{NS}<service>checkout-api{NS}</service>"
    f"{NS}<symptom>elevated 502s{NS}</symptom>"
    f"{NS}</invoke>\n"
    f"{NS}</tool_call>"
)
CHUNKS = ["<mm:think>", REASONING, "</mm:think>", TOOL_TEXT]
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH, trust_remote_code=True, local_files_only=True
)


def runtime_ids(chunk: str) -> list[int]:
    if chunk == "<mm:think>":
        return tokenizer.encode("<mm:", add_special_tokens=False) + tokenizer.encode(
            "think>", add_special_tokens=False
        )
    if chunk == "</mm:think>":
        return tokenizer.encode("</mm:", add_special_tokens=False) + tokenizer.encode(
            "think>", add_special_tokens=False
        )
    return tokenizer.encode(chunk, add_special_tokens=False)


def combined_parser(request: ChatCompletionRequest) -> Parser:
    parser_cls = ParserManager.get_parser(
        tool_parser_name="minimax_m3",
        reasoning_parser_name="minimax_m3",
        enable_auto_tools=True,
        model_name=request.model,
    )
    assert parser_cls is not None
    return parser_cls(tokenizer, request.tools or [])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("content-length", "0"))
        request = ChatCompletionRequest.model_validate_json(self.rfile.read(length))
        parser = combined_parser(request)
        if not request.stream:
            reasoning, content, tool_calls = parser.parse(
                "<mm:think>" + REASONING + "</mm:think>" + TOOL_TEXT,
                request,
                enable_auto_tools=True,
            )
            item = {
                "id": "chatcmpl-mcp-runbook-nonstream",
                "object": "chat.completion",
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "reasoning": reasoning,
                            "content": content,
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {
                                        "name": call.name,
                                        "arguments": call.arguments,
                                    },
                                }
                                for call in tool_calls or []
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            }
            encoded = json.dumps(item).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for index, chunk in enumerate(CHUNKS):
            delta = parser.parse_delta(
                chunk,
                runtime_ids(chunk),
                request,
                finished=index == len(CHUNKS) - 1,
            )
            if delta is None:
                continue
            item = {
                "id": "chatcmpl-mcp-runbook-repro",
                "object": "chat.completion.chunk",
                "model": request.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": delta.model_dump(exclude_none=False),
                        "finish_reason": None,
                    }
                ],
            }
            encoded = f"data: {json.dumps(item)}\n\n".encode()
            split_at = max(1, len(encoded) // 3)
            pieces = (
                encoded[:split_at],
                encoded[split_at : split_at * 2],
                encoded[split_at * 2 :],
            )
            for piece in pieces:
                self.wfile.write(piece)
                self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> int:
    request_body = {
        "model": "MiniMaxAI/MiniMax-M3-MXFP8",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Checkout API is returning elevated 502s. Search the current "
                    "incident runbooks for mitigation steps before answering."
                ),
            }
        ],
        "stream": True,
        "tool_choice": "auto",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_incident_runbooks",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string"},
                            "symptom": {"type": "string"},
                        },
                        "required": ["service", "symptom"],
                    },
                },
            }
        ],
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        received = []
        with httpx.stream(
            "POST",
            f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            json=request_body,
            timeout=10,
        ) as response:
            assert response.status_code == 200
            for line in response.iter_lines():
                if line.startswith("data: {"):
                    received.append(json.loads(line[6:])["choices"][0]["delta"])
        reasoning = "".join(delta.get("reasoning") or "" for delta in received)
        content = "".join(delta.get("content") or "" for delta in received)
        tool_calls = [
            call
            for delta in received
            for call in (delta.get("tool_calls") or [])
        ]
        print({"base_or_oracle_stream": received}, flush=True)
        nonstream_response = httpx.post(
            f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            json=request_body | {"stream": False},
            timeout=10,
        )
        assert nonstream_response.status_code == 200
        nonstream_body = nonstream_response.json()
        print({"base_or_oracle_nonstream": nonstream_body}, flush=True)
        nonstream_message = nonstream_body["choices"][0]["message"]
        assert nonstream_message["reasoning"] == REASONING
        assert nonstream_message["content"] is None
        assert len(nonstream_message["tool_calls"]) == 1
        assert nonstream_message["tool_calls"][0]["function"] == {
            "name": "search_incident_runbooks",
            "arguments": (
                '{"service":"checkout-api","symptom":"elevated 502s"}'
            ),
        }
        assert reasoning == REASONING
        assert content == ""
        assert "<mm:think>" not in content and "</mm:think>" not in content
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "search_incident_runbooks"
        assert tool_calls[0]["function"]["arguments"] == (
            '{"service":"checkout-api","symptom":"elevated 502s"}'
        )

        print(
            {
                "http_status": 200,
                "stream_reasoning": reasoning,
                "stream_content": content or None,
                "stream_tool": tool_calls[0]["function"],
                "nonstream_reasoning": nonstream_message["reasoning"],
                "nonstream_tool": nonstream_message["tool_calls"][0]["function"][
                    "name"
                ],
            },
            flush=True,
        )
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
