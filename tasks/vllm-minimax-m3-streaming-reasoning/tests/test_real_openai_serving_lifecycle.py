#!/usr/bin/env python3
"""Run MiniMax parsing through the real OpenAI serving lifecycle.

Only model execution is replaced. The pinned tokenizer, chat-template renderer,
request schema, OpenAIServingChat, registered parser, and SSE serialization are
the production vLLM implementations from the task base.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from vllm.config import MultiModalConfig
from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
from vllm.entrypoints.openai.chat_completion.serving import OpenAIServingChat
from vllm.entrypoints.openai.engine.protocol import ErrorResponse
from vllm.entrypoints.openai.models.protocol import BaseModelPath
from vllm.entrypoints.openai.models.serving import OpenAIServingModels
from vllm.outputs import CompletionOutput, RequestOutput
from vllm.renderers.hf import HfRenderer
from vllm.renderers.online_renderer import OnlineRenderer
from vllm.tokenizers import get_tokenizer


MODEL_PATH = "/opt/models/minimax-m3"
MODEL_NAME = "MiniMaxAI/MiniMax-M3-MXFP8"
NS = "]<]minimax[>["


@dataclass(frozen=True)
class Scenario:
    prompt: str
    reasoning: str
    tool_name: str
    arguments: dict[str, str]

    @property
    def tool_text(self) -> str:
        arguments = "".join(
            f"{NS}<{name}>{value}{NS}</{name}>"
            for name, value in self.arguments.items()
        )
        return (
            f"{NS}<tool_call>\n"
            f'{NS}<invoke name="{self.tool_name}">'
            f"{arguments}{NS}</invoke>\n{NS}</tool_call>"
        )


PRIMARY = Scenario(
    prompt=(
        "Checkout API is returning elevated 502s. Search the current incident "
        "runbooks for mitigation steps before answering."
    ),
    reasoning="I should search the current checkout incident runbook first.",
    tool_name="search_incident_runbooks",
    arguments={"service": "checkout-api", "symptom": "elevated 502s"},
)
HIDDEN_VARIATION = Scenario(
    prompt="Check the deployment record before explaining the worker failures.",
    reasoning="I should inspect the deployed release before answering.",
    tool_name="lookup_deployment",
    arguments={"release": "payments-2026.08.31"},
)


@dataclass
class MockHFConfig:
    model_type: str = "minimax_m3_vl"


@dataclass
class ModelConfig:
    task = "generate"
    runner_type = "generate"
    model = MODEL_NAME
    tokenizer = MODEL_PATH
    trust_remote_code = True
    tokenizer_mode = "auto"
    max_model_len = 4096
    tokenizer_revision = None
    multimodal_config = MultiModalConfig()
    hf_config = MockHFConfig()
    hf_text_config = MockHFConfig()
    logits_processors: list[str] | None = None
    diff_sampling_param: dict[str, Any] | None = None
    allowed_local_media_path = ""
    allowed_media_domains: list[str] | None = None
    encoder_config = None
    generation_config = "auto"
    override_generation_config: dict[str, Any] = field(default_factory=dict)
    media_io_kwargs: dict[str, dict[str, Any]] = field(default_factory=dict)
    skip_tokenizer_init = False
    is_encoder_decoder = False
    is_multimodal_model = False
    renderer_num_workers = 1
    enable_prompt_embeds = False

    def get_diff_sampling_param(self):
        return self.diff_sampling_param or {}


@dataclass
class ParallelConfig:
    _api_process_rank: int = 0


@dataclass
class VllmConfig:
    model_config: ModelConfig
    parallel_config: ParallelConfig


class DeterministicEngine:
    """Replace model execution while retaining the production serving path."""

    def __init__(self, renderer, tokenizer, *, streaming: bool):
        self.model_config = ModelConfig()
        self.renderer = renderer
        self.tokenizer = tokenizer
        self.streaming = streaming
        self.input_processor = None
        self.errored = False
        self.dead_error = RuntimeError("deterministic engine stopped")
        self.calls: list[dict[str, Any]] = []

    def _scenario(self, prompt: str) -> Scenario:
        for scenario in (PRIMARY, HIDDEN_VARIATION):
            if scenario.tool_name in prompt and scenario.prompt in prompt:
                return scenario
        raise AssertionError("rendered prompt did not contain a known scenario")

    def _split_marker_ids(self, marker: str) -> list[int]:
        prefix = "<mm:" if marker == "<mm:think>" else "</mm:"
        return self.tokenizer.encode(
            prefix, add_special_tokens=False
        ) + self.tokenizer.encode("think>", add_special_tokens=False)

    async def generate(self, engine_input, _sampling_params, request_id, **kwargs):
        prompt = engine_input["prompt"]
        prompt_token_ids = engine_input["prompt_token_ids"]
        scenario = self._scenario(prompt)
        parser_kwargs = kwargs.get("reasoning_parser_kwargs") or {}
        chat_template_kwargs = parser_kwargs.get("chat_template_kwargs") or {}
        thinking_mode = chat_template_kwargs.get("thinking_mode", "adaptive")
        self.calls.append(
            {
                "prompt": prompt,
                "prompt_token_ids": list(prompt_token_ids),
                "reasoning_ended": kwargs.get("reasoning_ended"),
                "thinking_mode": thinking_mode,
            }
        )

        if thinking_mode == "disabled":
            chunks = [scenario.tool_text]
            chunk_ids = [
                self.tokenizer.encode(scenario.tool_text, add_special_tokens=False)
            ]
        else:
            chunks = [scenario.reasoning, "</mm:think>", scenario.tool_text]
            chunk_ids = [
                self.tokenizer.encode(scenario.reasoning, add_special_tokens=False),
                self._split_marker_ids("</mm:think>"),
                self.tokenizer.encode(scenario.tool_text, add_special_tokens=False),
            ]
        if thinking_mode == "adaptive":
            chunks.insert(0, "<mm:think>")
            chunk_ids.insert(0, self._split_marker_ids("<mm:think>"))
        if not self.streaming:
            chunks = ["".join(chunks)]
            chunk_ids = [[token for part in chunk_ids for token in part]]

        for index, (text, token_ids) in enumerate(zip(chunks, chunk_ids)):
            finished = index == len(chunks) - 1
            yield RequestOutput(
                request_id=request_id,
                prompt=prompt,
                prompt_token_ids=prompt_token_ids,
                prompt_logprobs=None,
                outputs=[
                    CompletionOutput(
                        index=0,
                        text=text,
                        token_ids=token_ids,
                        cumulative_logprob=0.0,
                        logprobs=None,
                        finish_reason="stop" if finished else None,
                    )
                ],
                finished=finished,
            )

    async def abort(self, *_args, **_kwargs):
        return None


def request_body(
    scenario: Scenario,
    *,
    stream: bool,
    thinking_mode: str | None,
) -> dict[str, Any]:
    properties = {name: {"type": "string"} for name in scenario.arguments}
    body = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": scenario.prompt}],
        "stream": stream,
        "tool_choice": "auto",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": scenario.tool_name,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(scenario.arguments),
                    },
                },
            }
        ],
    }
    if thinking_mode is not None:
        body["chat_template_kwargs"] = {"thinking_mode": thinking_mode}
    return body


def build_app(*, streaming: bool):
    model_config = ModelConfig()
    tokenizer = get_tokenizer(MODEL_PATH, trust_remote_code=True)
    renderer = HfRenderer(
        VllmConfig(model_config, ParallelConfig()),
        tokenizer,
    )
    engine = DeterministicEngine(renderer, tokenizer, streaming=streaming)
    models = OpenAIServingModels(
        engine,
        [BaseModelPath(name=MODEL_NAME, model_path=MODEL_PATH)],
    )
    online_renderer = OnlineRenderer(
        model_config=model_config,
        renderer=renderer,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
        enable_auto_tools=True,
        tool_parser="minimax_m3",
        reasoning_parser="minimax_m3",
    )
    serving = OpenAIServingChat(
        engine,
        models,
        response_role="assistant",
        online_renderer=online_renderer,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
        reasoning_parser="minimax_m3",
        tool_parser="minimax_m3",
        enable_auto_tools=True,
    )
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(raw_request: Request):
        request = ChatCompletionRequest.model_validate(await raw_request.json())
        response = await serving.create_chat_completion(request)
        if isinstance(response, ErrorResponse):
            return JSONResponse(response.model_dump(mode="json"), status_code=400)
        if hasattr(response, "__aiter__"):
            return StreamingResponse(response, media_type="text/event-stream")
        return JSONResponse(response.model_dump(mode="json", exclude_none=True))

    return app, engine


def collect_stream(lines: list[str]) -> dict[str, Any]:
    chunks = [json.loads(line[6:]) for line in lines if line.startswith("data: {")]
    deltas = [choice["delta"] for chunk in chunks for choice in chunk["choices"]]
    reasoning = "".join(delta.get("reasoning") or "" for delta in deltas)
    content = "".join(delta.get("content") or "" for delta in deltas)
    tool_calls = [
        call for delta in deltas for call in (delta.get("tool_calls") or [])
    ]
    finish_reasons = [
        choice.get("finish_reason")
        for chunk in chunks
        for choice in chunk["choices"]
        if choice.get("finish_reason") is not None
    ]
    return {
        "reasoning": reasoning,
        "content": content,
        "tool_calls": tool_calls,
        "finish_reasons": finish_reasons,
        "chunks": chunks,
    }


def assert_result(
    result: dict[str, Any],
    scenario: Scenario,
    expected_mode: str,
) -> None:
    expected_reasoning = "" if expected_mode == "disabled" else scenario.reasoning
    assert result["reasoning"] == expected_reasoning
    assert result["content"] == ""
    assert "<mm:think>" not in result["reasoning"] + result["content"]
    assert "</mm:think>" not in result["reasoning"] + result["content"]
    assert len(result["tool_calls"]) == 1
    function = result["tool_calls"][0]["function"]
    assert function["name"] == scenario.tool_name
    assert json.loads(function["arguments"]) == scenario.arguments
    assert result["finish_reasons"] == ["tool_calls"]


async def run() -> None:
    stream_app, stream_engine = build_app(streaming=True)
    transport = httpx.ASGITransport(app=stream_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://minimax.local"
    ) as client:
        observed = []
        stream_cases = (
            (PRIMARY, None, "adaptive"),
            (PRIMARY, "enabled", "enabled"),
            (HIDDEN_VARIATION, None, "adaptive"),
            (HIDDEN_VARIATION, "enabled", "enabled"),
            (HIDDEN_VARIATION, "disabled", "disabled"),
            (PRIMARY, None, "adaptive"),
        )
        for scenario, request_mode, expected_mode in stream_cases:
            async with client.stream(
                "POST",
                "/v1/chat/completions",
                json=request_body(
                    scenario,
                    stream=True,
                    thinking_mode=request_mode,
                ),
            ) as response:
                assert response.status_code == 200
                result = collect_stream([line async for line in response.aiter_lines()])
            observed.append(result)

    nonstream_app, nonstream_engine = build_app(streaming=False)
    transport = httpx.ASGITransport(app=nonstream_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://minimax.local"
    ) as client:
        nonstream_messages = []
        nonstream_cases = (
            (None, "adaptive"),
            ("enabled", "enabled"),
            ("disabled", "disabled"),
        )
        for request_mode, expected_mode in nonstream_cases:
            response = await client.post(
                "/v1/chat/completions",
                json=request_body(
                    PRIMARY,
                    stream=False,
                    thinking_mode=request_mode,
                ),
            )
            assert response.status_code == 200
            nonstream_messages.append(response.json()["choices"][0]["message"])

    print(
        json.dumps(
            {
                "boundary": (
                    "ASGI POST -> ChatCompletionRequest -> real MiniMax chat-template "
                    "rendering -> OpenAIServingChat -> ParserManager -> SSE"
                ),
                "substitution": "model execution only",
                "adaptive_stream": {
                    k: v for k, v in observed[0].items() if k != "chunks"
                },
                "enabled_stream": {
                    k: v for k, v in observed[1].items() if k != "chunks"
                },
                "hidden_adaptive_stream": {
                    k: v for k, v in observed[2].items() if k != "chunks"
                },
                "hidden_enabled_stream": {
                    k: v for k, v in observed[3].items() if k != "chunks"
                },
                "hidden_disabled_stream": {
                    k: v for k, v in observed[4].items() if k != "chunks"
                },
                "repeat_adaptive_stream": {
                    k: v for k, v in observed[5].items() if k != "chunks"
                },
                "nonstream_messages": nonstream_messages,
                "engine_prompt_state_diagnostic": {
                    "stream": [
                        call["reasoning_ended"] for call in stream_engine.calls
                    ],
                    "nonstream": [
                        call["reasoning_ended"] for call in nonstream_engine.calls
                    ],
                },
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    for result, (scenario, _request_mode, expected_mode) in zip(
        observed, stream_cases
    ):
        assert_result(result, scenario, expected_mode)
    assert observed[0]["reasoning"] == observed[5]["reasoning"]
    assert observed[0]["tool_calls"][0]["function"] == observed[5]["tool_calls"][0][
        "function"
    ]
    for message, (_request_mode, expected_mode) in zip(
        nonstream_messages, nonstream_cases
    ):
        expected_reasoning = (
            None if expected_mode == "disabled" else PRIMARY.reasoning
        )
        assert message.get("reasoning") == expected_reasoning
        assert message.get("content") is None
        assert len(message["tool_calls"]) == 1
        assert message["tool_calls"][0]["function"]["name"] == PRIMARY.tool_name
        assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == (
            PRIMARY.arguments
        )


def main() -> int:
    try:
        asyncio.run(run())
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "message": str(exc).splitlines()[0] if str(exc) else "",
                }
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
