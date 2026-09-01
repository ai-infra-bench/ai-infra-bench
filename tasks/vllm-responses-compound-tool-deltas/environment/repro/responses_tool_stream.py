from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import uvicorn
from fastapi import FastAPI

from vllm.entrypoints.openai.engine.protocol import (
    DeltaFunctionCall,
    DeltaMessage,
    DeltaToolCall,
)
from vllm.entrypoints.openai.responses.api_router import attach_router
from vllm.entrypoints.openai.responses.serving import OpenAIServingResponses
from vllm.inputs import tokens_input
from vllm.outputs import CompletionOutput, RequestOutput


EXPECTED = '{"path":"/tmp/x.py","content":"print(\\"hi\\")"}'


class DeterministicParser:
    reasoning_parser = MagicMock()
    tool_parser = None

    def __init__(self) -> None:
        self.used = False

    def parse_delta(self, **_kwargs):
        if self.used:
            return None
        self.used = True
        return DeltaMessage(
            tool_calls=[
                DeltaToolCall(
                    index=0,
                    id="call_write",
                    type="function",
                    function=DeltaFunctionCall(name="write"),
                ),
                DeltaToolCall(
                    index=0,
                    function=DeltaFunctionCall(arguments=EXPECTED),
                ),
            ]
        )

    def is_reasoning_end(self, *_args, **_kwargs) -> bool:
        return False

    def extract_response_outputs(self, **_kwargs) -> list:
        return []


class ParserFactory:
    reasoning_parser_cls = None
    tool_parser_cls = None

    def __call__(self, *_args, **_kwargs) -> DeterministicParser:
        return DeterministicParser()


def serving() -> OpenAIServingResponses:
    engine = MagicMock()
    engine.errored = False
    engine.model_config.max_model_len = 4096
    engine.model_config.model = "moonshotai/Kimi-K2.5"
    engine.model_config.generation_config = "vllm"
    engine.model_config.override_generation_config = {}
    engine.model_config.hf_config.model_type = "test"
    engine.model_config.hf_text_config = MagicMock()
    engine.model_config.get_diff_sampling_param.return_value = {}
    engine.input_processor = MagicMock()
    engine.renderer = MagicMock()
    engine.renderer.get_tokenizer.return_value = MagicMock()
    engine.is_tracing_enabled = AsyncMock(return_value=False)

    async def generate(*_args, **_kwargs) -> AsyncIterator[RequestOutput]:
        yield RequestOutput(
            request_id="req",
            prompt="prompt",
            prompt_token_ids=[1, 2],
            prompt_logprobs=None,
            outputs=[
                CompletionOutput(
                    index=0,
                    text="model update",
                    token_ids=[10],
                    cumulative_logprob=0.0,
                    logprobs=None,
                    finish_reason="stop",
                    stop_reason=None,
                )
            ],
            finished=True,
            num_cached_tokens=0,
        )

    engine.generate = generate
    render = MagicMock()
    render.preprocess_chat = AsyncMock(
        return_value=([], [tokens_input([1, 2])])
    )
    models = MagicMock()
    models.is_base_model.return_value = True
    models.model_name.return_value = "moonshotai/Kimi-K2.5"
    models.lora_requests = {}
    handler = OpenAIServingResponses(
        engine_client=engine,
        models=models,
        openai_serving_render=render,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
    )
    handler.parser = ParserFactory()
    return handler


def main() -> int:
    app = FastAPI()
    attach_router(app)
    app.state.openai_serving_responses = serving()

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

    request = {
        "model": "moonshotai/Kimi-K2.5",
        "stream": True,
        "store": False,
        "input": (
            'Call the write tool to put print("hi") into /tmp/x.py. '
            "No explanation."
        ),
        "tools": [
            {
                "type": "function",
                "name": "write",
                "description": "Write content to a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            }
        ],
    }
    events = []
    try:
        with httpx.stream(
            "POST",
            f"http://127.0.0.1:{port}/v1/responses",
            json=request,
            timeout=30,
        ) as response:
            print(f"POST /v1/responses {response.status_code}")
            for line in response.iter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    events.append(event)
                    print(f"{event['type']}: {line[6:]}")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()

    done = next(
        event["item"]["arguments"]
        for event in events
        if event["type"] == "response.output_item.done"
        and event["item"]["type"] == "function_call"
    )
    try:
        parsed = json.loads(done)
    except json.JSONDecodeError as error:
        print(f"done.arguments={done!r}")
        print(f"json_error={error.msg}")
        return 3
    print(f"done.arguments={done!r}")
    print(f"matches_request={parsed == json.loads(EXPECTED)}")
    return 0 if parsed == json.loads(EXPECTED) else 3


if __name__ == "__main__":
    raise SystemExit(main())
