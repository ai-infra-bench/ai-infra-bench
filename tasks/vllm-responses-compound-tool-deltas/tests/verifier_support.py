from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from vllm.entrypoints.openai.engine.protocol import DeltaMessage
from vllm.entrypoints.openai.responses.protocol import ResponsesRequest
from vllm.entrypoints.openai.responses.serving import OpenAIServingResponses
from vllm.inputs import tokens_input
from vllm.outputs import CompletionOutput, RequestOutput


def function_tool(name: str) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": f"Invoke {name}.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "query": {"type": "string"},
            },
            "additionalProperties": True,
        },
    }


def responses_request(*, tools: list[str] | None = None) -> ResponsesRequest:
    return ResponsesRequest(
        model="moonshotai/Kimi-K2.5",
        input="Use the available tools.",
        tools=[function_tool(name) for name in (tools or ["write"])],
        tool_choice="auto",
        stream=True,
        store=False,
    )


def kimi_bash_request() -> ResponsesRequest:
    return ResponsesRequest(
        model="moonshotai/Kimi-K2.5",
        input="Inspect the repository and continue the task.",
        tools=[
            {
                "type": "function",
                "name": "bash",
                "description": "Execute a bash command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute",
                        }
                    },
                    "required": ["command"],
                },
            }
        ],
        tool_choice="auto",
        stream=True,
        store=False,
    )


class _DeterministicParser:
    reasoning_parser = MagicMock()
    tool_parser = None

    def __init__(self, deltas: list[DeltaMessage]) -> None:
        self._deltas = iter(deltas)

    def parse_delta(self, **_kwargs):
        return next(self._deltas, None)

    def is_reasoning_end(self, *_args, **_kwargs) -> bool:
        return False

    def extract_response_outputs(self, **_kwargs) -> list:
        return []


class _ParserFactory:
    reasoning_parser_cls = None
    tool_parser_cls = None

    def __init__(self, deltas: list[DeltaMessage]) -> None:
        self._deltas = deltas

    def __call__(self, *_args, **_kwargs) -> _DeterministicParser:
        return _DeterministicParser(self._deltas)


def build_serving(
    delta_sequence: list[DeltaMessage],
    *,
    output_text: str = "",
    use_parser: bool = True,
) -> OpenAIServingResponses:
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
        count = max(1, len(delta_sequence))
        for index in range(count):
            last = index == count - 1
            yield RequestOutput(
                request_id="req",
                prompt="prompt",
                prompt_token_ids=[1, 2],
                prompt_logprobs=None,
                outputs=[
                    CompletionOutput(
                        index=0,
                        text=output_text or f"chunk-{index}",
                        token_ids=[index + 10],
                        cumulative_logprob=0.0,
                        logprobs=None,
                        finish_reason="stop" if last else None,
                        stop_reason=None,
                    )
                ],
                finished=last,
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

    serving = OpenAIServingResponses(
        engine_client=engine,
        models=models,
        openai_serving_render=render,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
    )
    serving.parser = _ParserFactory(delta_sequence) if use_parser else None
    return serving


def build_kimi_serving(model_chunks: list[str]) -> OpenAIServingResponses:
    """Use real Kimi parsing while replacing only unavailable model generation."""
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
        for index, chunk in enumerate(model_chunks):
            last = index == len(model_chunks) - 1
            yield RequestOutput(
                request_id="req",
                prompt="prompt",
                prompt_token_ids=[1, 2],
                prompt_logprobs=None,
                outputs=[
                    CompletionOutput(
                        index=0,
                        text=chunk,
                        token_ids=[index + 100],
                        cumulative_logprob=0.0,
                        logprobs=None,
                        finish_reason="stop" if last else None,
                        stop_reason=None,
                    )
                ],
                finished=last,
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

    return OpenAIServingResponses(
        engine_client=engine,
        models=models,
        openai_serving_render=render,
        request_logger=None,
        chat_template=None,
        chat_template_content_format="auto",
        tool_parser="kimi_k2",
        enable_auto_tools=True,
    )


async def collect_nonstream_text(text: str) -> dict:
    serving = build_serving(
        [DeltaMessage(content=text)],
        output_text=text,
        use_parser=False,
    )
    response = await serving.create_responses(
        ResponsesRequest(
            model="moonshotai/Kimi-K2.5",
            input="Return plain text.",
            tools=[],
            stream=False,
            store=False,
        )
    )
    return response.model_dump(mode="json")


async def collect_events(
    delta_sequence: list[DeltaMessage],
    request: ResponsesRequest | None = None,
) -> list[dict]:
    serving = build_serving(delta_sequence)
    response = await serving.create_responses(request or responses_request())
    events = []
    async for event in response:
        events.append(event.model_dump(mode="json"))
    return events


async def collect_kimi_events(
    model_chunks: list[str],
    *,
    serving: OpenAIServingResponses | None = None,
) -> list[dict]:
    handler = serving or build_kimi_serving(model_chunks)
    response = await handler.create_responses(kimi_bash_request())
    events = []
    async for event in response:
        events.append(event.model_dump(mode="json"))
    return events


def argument_deltas(events: list[dict]) -> list[str]:
    return [
        event["delta"]
        for event in events
        if event["type"] == "response.function_call_arguments.delta"
    ]


def completed_calls(events: list[dict]) -> list[dict]:
    return [
        event["item"]
        for event in events
        if event["type"] == "response.output_item.done"
        and event["item"]["type"] == "function_call"
    ]
