from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from verifier_support import (
    RustServer,
    assert_count_matches_generation,
    assert_json_constraint,
    minimax_parallel_tool_calls,
    minimax_tool_call,
)


MODEL = "local-model"


def client(base_url: str, api_key: str = "test-key") -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url,
        max_retries=0,
        timeout=20,
        _strict_response_validation=True,
    )


def test_existing_rust_openai_and_health_routes(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["openai regression"]) as server:
        health = httpx2.get(f"{server.base_url}/health", timeout=20)
        models = httpx2.get(f"{server.base_url}/v1/models", timeout=20)
        chat = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": MODEL,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "OPENAI_CHAT_CONTROL"}],
            },
            timeout=20,
        )
        completion = httpx2.post(
            f"{server.base_url}/v1/completions",
            json={
                "model": MODEL,
                "max_tokens": 8,
                "prompt": "OPENAI_COMPLETION_CONTROL",
            },
            timeout=20,
        )
    assert health.status_code == 200
    assert models.status_code == 200
    assert models.json()["data"][0]["id"] == MODEL
    assert chat.status_code == 200
    assert completion.status_code == 200


def create_kwargs(**extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "SDK_MATRIX_HELLO"}],
    }
    result.update(extra)
    return result


def tool_definition() -> dict[str, Any]:
    return {
        "type": "custom",
        "name": "get_weather",
        "description": "Return weather for one city",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "unit": {"type": "string"},
            },
            "required": ["city"],
        },
        "strict": True,
    }


def test_sync_nonstream_raw_and_streaming_response(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["plain response"], cached_tokens=3) as server:
        sdk = client(server.base_url)
        message = sdk.messages.create(**create_kwargs())
        assert message.type == "message"
        assert message.role == "assistant"
        assert message.model == MODEL
        assert message.content[0].type == "text"
        assert "plain response" in message.content[0].text
        assert message.stop_reason == "end_turn"
        assert message.usage.input_tokens > 0
        assert message.usage.output_tokens > 0
        assert message.usage.cache_read_input_tokens == 3
        assert message.usage.cache_creation_input_tokens in (None, 0)

        raw = sdk.messages.with_raw_response.create(**create_kwargs())
        assert raw.status_code == 200
        assert raw.parse().content[0].type == "text"

        with sdk.messages.with_streaming_response.create(**create_kwargs()) as response:
            assert response.status_code == 200
            assert response.parse().content[0].type == "text"


@pytest.mark.asyncio
async def test_async_nonstream_and_stream(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["async response"], chunk_sizes=[1, 2, 3, 1]) as server:
        async with anthropic.AsyncAnthropic(
            api_key="test-key",
            base_url=server.base_url,
            max_retries=0,
            timeout=20,
            _strict_response_validation=True,
        ) as sdk:
            message = await sdk.messages.create(**create_kwargs())
            assert "async response" in message.content[0].text
            raw = await sdk.messages.with_raw_response.create(**create_kwargs())
            assert (await raw.parse()).role == "assistant"
            async with sdk.messages.with_streaming_response.create(
                **create_kwargs()
            ) as response:
                assert (await response.parse()).role == "assistant"
            count = await sdk.messages.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "async count"}],
            )
            assert count.input_tokens > 0
            raw_count = await sdk.messages.with_raw_response.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "async raw count"}],
            )
            assert (await raw_count.parse()).input_tokens > 0
            async with sdk.messages.with_streaming_response.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "async response count"}],
            ) as response:
                assert (await response.parse()).input_tokens > 0
            async with sdk.messages.stream(**create_kwargs()) as stream:
                events = [event async for event in stream]
                final = await stream.get_final_message()
            raw_stream = await sdk.messages.create(**create_kwargs(stream=True))
            raw_events = [event async for event in raw_stream]
            await raw_stream.close()
        assert events[0].type == "message_start"
        assert events[-1].type == "message_stop"
        assert "async response" in final.content[0].text
        assert raw_events[-1].type == "message_stop"


def test_stream_helper_event_order_and_accumulation(tmp_path: Path) -> None:
    with RustServer(
        tmp_path,
        ["chunked response"],
        chunk_sizes=[1, 3, 2, 4],
        cached_tokens=3,
    ) as server:
        with client(server.base_url).messages.stream(**create_kwargs()) as stream:
            events = list(stream)
            final = stream.get_final_message()
        event_types = [event.type for event in events]
        assert event_types[0] == "message_start"
        assert event_types[-1] == "message_stop"
        assert event_types.count("content_block_start") == 1
        assert event_types.count("content_block_stop") == 1
        assert event_types.count("message_delta") == 1
        assert final.content[0].text == "chunked response"
        assert final.usage.cache_read_input_tokens == 3


def test_count_tokens_is_stable_sensitive_and_generation_free(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["unused generation"]) as server:
        sdk = client(server.base_url)

        def count_with_tokenizer_observation(**kwargs: Any) -> int:
            return assert_count_matches_generation(sdk, server, **kwargs)

        short = count_with_tokenizer_observation(
            model=MODEL, messages=[{"role": "user", "content": "short"}]
        )
        repeated = count_with_tokenizer_observation(
            model=MODEL, messages=[{"role": "user", "content": "short"}]
        )
        long = count_with_tokenizer_observation(
            model=MODEL,
            system="COUNT_SYSTEM_SENTINEL",
            messages=[
                {"role": "user", "content": "short with substantially more content"}
            ],
            tools=[tool_definition()],
        )
        assert short > 0
        assert repeated == short
        assert long > short


class Weather(BaseModel):
    city: str
    temperature: int


def test_parse_structured_output(tmp_path: Path) -> None:
    output = '{"city":"Paris","temperature":21}'
    with RustServer(tmp_path, [output]) as server:
        message = client(server.base_url).messages.parse(
            **create_kwargs(),
            output_format=Weather,
        )
        block = message.content[0]
        assert block.type == "text"
        assert block.parsed_output == Weather(city="Paris", temperature=21)
        assert_json_constraint(server.captures()[-1], Weather.model_json_schema())


@pytest.mark.parametrize(
    ("tool_choice", "expected_choice", "expected_parallel"),
    [
        ({"type": "auto", "disable_parallel_tool_use": False}, "auto", True),
        ({"type": "any", "disable_parallel_tool_use": True}, "required", False),
        (
            {
                "type": "tool",
                "name": "get_weather",
                "disable_parallel_tool_use": False,
            },
            "function",
            True,
        ),
        ({"type": "none"}, "none", True),
    ],
)
def test_tool_choice_request_semantics(
    tmp_path: Path,
    tool_choice: dict[str, Any],
    expected_choice: str,
    expected_parallel: bool,
) -> None:
    output = minimax_tool_call("get_weather", [("city", "Paris"), ("unit", "c")])
    with RustServer(tmp_path, [output], tool_parser="minimax_m2") as server:
        message = client(server.base_url).messages.create(
            **create_kwargs(tools=[tool_definition()], tool_choice=tool_choice)
        )
        semantic_request = server.render_captures()[-1]["chat_request"]
        serialized_choice = json.dumps(semantic_request["tool_choice"])
        assert expected_choice in serialized_choice.lower()
        assert semantic_request["parallel_tool_calls"] is expected_parallel
        if tool_choice["type"] == "none":
            assert all(block.type != "tool_use" for block in message.content)
        else:
            calls = [block for block in message.content if block.type == "tool_use"]
            assert len(calls) == 1
            assert calls[0].name == "get_weather"
            assert calls[0].input == {"city": "Paris", "unit": "c"}


def test_parallel_tool_calls_nonstream(tmp_path: Path) -> None:
    output = minimax_parallel_tool_calls(["Paris", "Tokyo"])
    with RustServer(tmp_path, [output], tool_parser="minimax_m2") as server:
        message = client(server.base_url).messages.create(
            **create_kwargs(
                tools=[tool_definition()],
                tool_choice={"type": "auto", "disable_parallel_tool_use": False},
            )
        )
        calls = [block for block in message.content if block.type == "tool_use"]
        assert message.stop_reason == "tool_use"
        assert len(calls) == 2
        assert len({call.id for call in calls}) == 2
        assert [call.input["city"] for call in calls] == ["Paris", "Tokyo"]


def test_parallel_tool_calls_stream_with_fragmented_arguments(tmp_path: Path) -> None:
    output = minimax_parallel_tool_calls(["Oslo", "Lima"])
    with RustServer(
        tmp_path,
        [output],
        tool_parser="minimax_m2",
        chunk_sizes=[1, 5, 2, 7, 3, 1],
    ) as server:
        with client(server.base_url).messages.stream(
            **create_kwargs(
                tools=[tool_definition()],
                tool_choice={"type": "auto", "disable_parallel_tool_use": False},
            )
        ) as stream:
            events = list(stream)
            final = stream.get_final_message()
        calls = [block for block in final.content if block.type == "tool_use"]
        assert len(calls) == 2
        assert [call.input["city"] for call in calls] == ["Oslo", "Lima"]
        starts = [event for event in events if event.type == "content_block_start"]
        assert len(starts) == 2
        assert [event.index for event in starts] == [0, 1]


@pytest.mark.parametrize(
    ("finish_reason", "stop_text", "expected_reason", "expected_sequence"),
    [
        ("stop", "HALT", "stop_sequence", "HALT"),
        ("length", None, "max_tokens", None),
    ],
)
def test_finish_reason_mapping(
    tmp_path: Path,
    finish_reason: str,
    stop_text: str | None,
    expected_reason: str,
    expected_sequence: str | None,
) -> None:
    with RustServer(
        tmp_path,
        ["finished"],
        finish_reason=finish_reason,
        stop_text=stop_text,
    ) as server:
        sdk = client(server.base_url)
        message = sdk.messages.create(**create_kwargs())
        with sdk.messages.stream(**create_kwargs()) as stream:
            streamed = stream.get_final_message()
    for result in (message, streamed):
        assert result.stop_reason == expected_reason
        assert result.stop_sequence == expected_sequence


@pytest.mark.parametrize("marker", ["FIRST_STOP", "SECOND_STOP"])
def test_requested_stop_sequence_is_applied(tmp_path: Path, marker: str) -> None:
    with RustServer(
        tmp_path, [f"visible{marker}hidden"], chunk_sizes=[1] * 128
    ) as server:
        message = client(server.base_url).messages.create(
            **create_kwargs(stop_sequences=["FIRST_STOP", "SECOND_STOP"])
        )
        assert message.content[0].text == "visible"
        assert message.stop_reason == "stop_sequence"
        assert message.stop_sequence == marker


def test_rich_history_reaches_semantic_engine_input(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["history accepted"]) as server:
        client(server.base_url).messages.create(
            model=MODEL,
            max_tokens=128,
            system="TOP_LEVEL_SYSTEM_SENTINEL",
            messages=[
                {"role": "system", "content": "INLINE_SYSTEM_SENTINEL"},
                {"role": "user", "content": "FIRST_USER_SENTINEL"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "HISTORY_REASONING_SENTINEL",
                            "signature": "history-signature",
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_history",
                            "name": "get_weather",
                            "input": {"city": "Berlin"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_history",
                            "content": "HISTORY_TOOL_RESULT_SENTINEL",
                        }
                    ],
                },
                {"role": "user", "content": "FINAL_USER_SENTINEL"},
            ],
            tools=[tool_definition()],
            tool_choice={"type": "auto", "disable_parallel_tool_use": False},
            stop_sequences=["STOP_SENTINEL"],
            metadata={"user_id": "metadata-sentinel"},
        )
        prompt = server.captures()[-1]["prompt"]
        for sentinel in (
            "TOP_LEVEL_SYSTEM_SENTINEL",
            "INLINE_SYSTEM_SENTINEL",
            "FIRST_USER_SENTINEL",
            "HISTORY_REASONING_SENTINEL",
            "get_weather",
            "Berlin",
            "HISTORY_TOOL_RESULT_SENTINEL",
            "FINAL_USER_SENTINEL",
        ):
            assert sentinel in prompt


@pytest.mark.asyncio
async def test_concurrent_requests_have_isolated_content_and_ids(
    tmp_path: Path,
) -> None:
    outputs = [f"concurrent-{index}" for index in range(8)]
    with RustServer(tmp_path, outputs) as server:
        async with anthropic.AsyncAnthropic(
            api_key="test-key",
            base_url=server.base_url,
            max_retries=0,
            timeout=20,
            _strict_response_validation=True,
        ) as sdk:
            messages = await asyncio.gather(
                *[
                    sdk.messages.create(
                        **create_kwargs(
                            messages=[
                                {
                                    "role": "user",
                                    "content": f"CONCURRENT_INPUT_{index}",
                                }
                            ]
                        )
                    )
                    for index in range(8)
                ]
            )
        assert len({message.id for message in messages}) == 8
        assert {message.content[0].text for message in messages} == set(outputs)
        captured = "\n".join(item["prompt"] for item in server.captures())
        for index in range(8):
            assert captured.count(f"CONCURRENT_INPUT_{index}") == 1
