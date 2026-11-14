from argparse import Namespace
from http import HTTPStatus

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from vllm.entrypoints.cohere.api_router import attach_router
from vllm.entrypoints.cohere.protocol import (
    AssistantMessageResponse,
    CohereChatV2Response,
)
from vllm.entrypoints.scale_out.token_in_token_out.protocol import GenerateRequest
from vllm.entrypoints.serve.exception_handling.handlers.http import (
    http_exception_handler,
)
from vllm.entrypoints.serve.exception_handling.handlers.validation import (
    validation_exception_handler,
)
from vllm.entrypoints.serve.exception_handling.handlers.vllm_error import (
    vllm_error_handler,
)
from vllm.exceptions import VLLMError
from vllm.sampling_params import SamplingParams


PATHS = ("/cohere/v2/chat", "/cohere/v2/chat/render")
TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_weather",
        "description": "Look up the weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


class RecordingChatHandler:
    def __init__(self) -> None:
        self.chat_calls = 0
        self.conversion_calls = 0

    async def create_chat_v2(self, request, raw_request):
        self.chat_calls += 1
        message = AssistantMessageResponse(
            content=[{"type": "text", "text": "ok"}]
        )
        return CohereChatV2Response(
            id="response-1",
            finish_reason="COMPLETE",
            message=message,
        )

    def to_chat_completion_request(self, request):
        self.conversion_calls += 1
        return request

    def _engine_chat_template_kwargs(self, chat_template_kwargs):
        return chat_template_kwargs


class RecordingRenderHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def render_chat_request(self, request):
        self.calls += 1
        return GenerateRequest(
            request_id="render-1",
            token_ids=[1, 2, 3],
            sampling_params=SamplingParams(temperature=0.0),
            model="m",
        )


def build_app(monkeypatch):
    monkeypatch.setenv("VLLM_ENABLE_COHERE_API", "1")
    app = FastAPI()
    app.state.args = Namespace(
        log_error_stack=False,
        enable_scale_out=True,
        tokens_only=False,
    )
    attach_router(app)
    chat_handler = RecordingChatHandler()
    render_handler = RecordingRenderHandler()
    app.state.cohere_serving_chat_v2 = chat_handler
    app.state.serving_render = render_handler
    app.exception_handler(RequestValidationError)(validation_exception_handler)
    app.exception_handler(HTTPException)(http_exception_handler)
    app.exception_handler(VLLMError)(vllm_error_handler)
    return app, chat_handler, render_handler


def request_body(*, tool_choice_marker="missing", tools_marker="missing"):
    body = {
        "model": "m",
        "messages": [{"role": "user", "content": "Use a tool if needed."}],
    }
    if tool_choice_marker != "missing":
        body["tool_choice"] = tool_choice_marker
    if tools_marker != "missing":
        body["tools"] = tools_marker
    return body


def assert_downstream_calls(path, chat_handler, render_handler, expected):
    if path == "/cohere/v2/chat":
        assert chat_handler.chat_calls == expected
        assert chat_handler.conversion_calls == 0
        assert render_handler.calls == 0
    else:
        assert chat_handler.chat_calls == 0
        assert chat_handler.conversion_calls == expected
        assert render_handler.calls == expected


@pytest.mark.parametrize("path", PATHS, ids=["chat", "render"])
@pytest.mark.parametrize(
    "tools_marker",
    ["missing", None, []],
    ids=["tools-omitted", "tools-null", "tools-empty"],
)
def test_required_without_available_tools_is_rejected_before_handler(
    monkeypatch, path, tools_marker
):
    app, chat_handler, render_handler = build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            path,
            json=request_body(
                tool_choice_marker="REQUIRED",
                tools_marker=tools_marker,
            ),
        )

    assert response.status_code == HTTPStatus.BAD_REQUEST
    payload = response.json()
    assert "error" not in payload
    assert isinstance(payload.get("message"), str) and payload["message"]
    assert "REQUIRED" in payload["message"]
    assert "tool" in payload["message"].lower()
    assert_downstream_calls(path, chat_handler, render_handler, 0)


@pytest.mark.parametrize("path", PATHS, ids=["chat", "render"])
def test_required_with_a_tool_reaches_handler(monkeypatch, path):
    app, chat_handler, render_handler = build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            path,
            json=request_body(
                tool_choice_marker="REQUIRED",
                tools_marker=[TOOL],
            ),
        )

    assert response.status_code == HTTPStatus.OK
    assert_downstream_calls(path, chat_handler, render_handler, 1)


@pytest.mark.parametrize("path", PATHS, ids=["chat", "render"])
@pytest.mark.parametrize(
    "tools_marker",
    ["missing", None, []],
    ids=["tools-omitted", "tools-null", "tools-empty"],
)
@pytest.mark.parametrize(
    "tool_choice_marker",
    ["missing", "NONE"],
    ids=["choice-omitted", "choice-none"],
)
def test_nonrequired_choice_preserves_empty_tool_behavior(
    monkeypatch, path, tools_marker, tool_choice_marker
):
    app, chat_handler, render_handler = build_app(monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            path,
            json=request_body(
                tool_choice_marker=tool_choice_marker,
                tools_marker=tools_marker,
            ),
        )

    assert response.status_code == HTTPStatus.OK
    assert_downstream_calls(path, chat_handler, render_handler, 1)
