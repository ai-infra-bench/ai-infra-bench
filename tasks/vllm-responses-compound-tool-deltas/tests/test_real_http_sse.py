from __future__ import annotations

import json
import socket
import threading
import time

import httpx
import uvicorn
from fastapi import FastAPI

from vllm.entrypoints.openai.engine.protocol import (
    DeltaFunctionCall,
    DeltaMessage,
    DeltaToolCall,
)
from vllm.entrypoints.openai.responses.api_router import attach_router

from verifier_support import build_serving


def tool(index: int, *, name: str | None = None, arguments: str | None = None):
    return DeltaToolCall(
        index=index,
        function=DeltaFunctionCall(name=name, arguments=arguments),
    )


def request_body(prompt: str, *, parallel: bool = False) -> dict:
    tools = [
        {
            "type": "function",
            "name": "write",
            "description": "Write a file.",
            "parameters": {"type": "object", "additionalProperties": True},
        }
    ]
    if parallel:
        tools.append(
            {
                "type": "function",
                "name": "search",
                "description": "Search incident records.",
                "parameters": {"type": "object", "additionalProperties": True},
            }
        )
    return {
        "model": "moonshotai/Kimi-K2.5",
        "input": prompt,
        "stream": True,
        "store": False,
        "tool_choice": "auto",
        "tools": tools,
    }


def read_events(url: str, body: dict) -> list[dict]:
    events = []
    with httpx.stream("POST", url, json=body, timeout=30) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        for line in response.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def completed_calls(events: list[dict]) -> list[dict]:
    return [
        event["item"]
        for event in events
        if event["type"] == "response.output_item.done"
        and event["item"]["type"] == "function_call"
    ]


def parsed_arguments(call: dict) -> dict | None:
    try:
        value = json.loads(call["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def main() -> int:
    app = FastAPI()
    attach_router(app)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started

    root = f"http://127.0.0.1:{port}/v1/responses"
    try:
        app.state.openai_serving_responses = build_serving(
            [
                DeltaMessage(
                    reasoning="The user requested a file.",
                    tool_calls=[
                        tool(0, name="write"),
                        tool(
                            0,
                            arguments=(
                                '{"path":"/tmp/x.py",'
                                '"content":"print(\\"hi\\")"}'
                            ),
                        ),
                    ],
                )
            ]
        )
        one = read_events(root, request_body("Write the generated file."))
        one_calls = completed_calls(one)
        one_arguments = parsed_arguments(one_calls[0]) if len(one_calls) == 1 else None

        app.state.openai_serving_responses = build_serving(
            [
                DeltaMessage(
                    content="Running both tools.",
                    tool_calls=[
                        tool(
                            0,
                            name="write",
                            arguments='{"path":"/tmp/a","content":"A"}',
                        ),
                        tool(
                            1,
                            name="search",
                            arguments='{"query":"incident B"}',
                        ),
                    ],
                )
            ]
        )
        parallel = read_events(
            root,
            request_body("Use parallel tools.", parallel=True),
        )
        parallel_calls = completed_calls(parallel)
        parallel_arguments = [parsed_arguments(call) for call in parallel_calls]
        single_valid = one_arguments == {
            "path": "/tmp/x.py",
            "content": 'print("hi")',
        }
        parallel_valid = (
            [call["name"] for call in parallel_calls] == ["write", "search"]
            and parallel_arguments
            == [
            {"path": "/tmp/a", "content": "A"},
            {"query": "incident B"},
            ]
        )
        print(
            json.dumps(
                {
                    "entrypoint": "real vLLM POST /v1/responses router over TCP",
                    "single_tool_events": len(one),
                    "parallel_tool_events": len(parallel),
                    "completed_calls": len(one_calls) + len(parallel_calls),
                    "single_tool_valid": single_valid,
                    "parallel_tools_valid": parallel_valid,
                },
                separators=(",", ":"),
            )
        )
        assert single_valid
        assert parallel_valid
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


if __name__ == "__main__":
    raise SystemExit(main())
