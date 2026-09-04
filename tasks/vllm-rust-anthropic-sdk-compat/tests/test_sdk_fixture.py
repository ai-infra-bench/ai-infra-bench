from __future__ import annotations

import importlib.metadata
from typing import Any

import anthropic
import pytest
from pydantic import BaseModel

from protocol_fixture import FixtureServer


MODEL = "local-model"


def _client(base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="fixture-key",
        base_url=base_url,
        max_retries=0,
        timeout=10,
        _strict_response_validation=True,
    )


def _kwargs(case: str = "text") -> dict[str, Any]:
    return {
        "model": MODEL,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Hello"}],
        "extra_headers": {"x-ai-infra-case": case},
    }


def test_exact_sdk_version() -> None:
    assert importlib.metadata.version("anthropic") == "1.3.0"


def test_sync_create_and_raw_response() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        message = client.messages.create(**_kwargs())
        assert message.type == "message"
        assert message.role == "assistant"
        assert message.content[0].type == "text"
        assert message.content[0].text == "fixture response"
        assert message.usage.output_tokens_details is not None
        assert message.usage.output_tokens_details.thinking_tokens == 2

        raw = client.messages.with_raw_response.create(**_kwargs())
        assert raw.request_id == "req_fixture_123"
        assert raw.parse().content[0].text == "fixture response"


@pytest.mark.asyncio
async def test_async_create_parallel_tools() -> None:
    with FixtureServer() as server:
        async with anthropic.AsyncAnthropic(
            api_key="fixture-key",
            base_url=server.base_url,
            max_retries=0,
            timeout=10,
            _strict_response_validation=True,
        ) as client:
            message = await client.messages.create(**_kwargs("parallel_tools"))
            raw = await client.messages.with_raw_response.create(
                **_kwargs("parallel_tools")
            )
            parsed_raw = await raw.parse()
            async with client.messages.with_streaming_response.create(
                **_kwargs("parallel_tools")
            ) as response:
                parsed_streaming_response = await response.parse()
            count = await client.messages.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "Count async"}],
            )
            raw_count = await client.messages.with_raw_response.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "Count async raw"}],
            )
            parsed_raw_count = await raw_count.parse()
            async with client.messages.with_streaming_response.count_tokens(
                model=MODEL,
                messages=[{"role": "user", "content": "Count async response"}],
            ) as response:
                parsed_streaming_count = await response.parse()
            parsed_message = await client.messages.parse(
                **_kwargs("parse"),
                output_format=Weather,
            )
        calls = [block for block in message.content if block.type == "tool_use"]
        assert message.stop_reason == "tool_use"
        assert [call.id for call in calls] == [
            "toolu_weather_paris",
            "toolu_weather_tokyo",
        ]
        assert [call.input["city"] for call in calls] == ["Paris", "Tokyo"]
        assert parsed_raw.stop_reason == "tool_use"
        assert parsed_streaming_response.stop_reason == "tool_use"
        assert count.input_tokens == 37
        assert parsed_raw_count.input_tokens == 37
        assert parsed_streaming_count.input_tokens == 37
        assert parsed_message.content[0].parsed_output == Weather(
            city="Paris", temperature=21
        )


def test_sync_stream_text_and_thinking() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        with client.messages.stream(**_kwargs("stream_text")) as stream:
            events = list(stream)
            message = stream.get_final_message()
        assert message.content[0].text == "fixture stream"
        assert events[0].type == "message_start"
        assert events[-1].type == "message_stop"

        raw_stream = client.messages.create(
            **_kwargs("stream_text"),
            stream=True,
        )
        raw_events = list(raw_stream)
        raw_stream.close()
        assert raw_events[0].type == "message_start"
        assert raw_events[-1].type == "message_stop"

        raw_response = client.messages.with_raw_response.create(
            **_kwargs("stream_text"),
            stream=True,
        )
        parsed_stream = raw_response.parse()
        parsed_events = list(parsed_stream)
        parsed_stream.close()
        assert parsed_events[-1].type == "message_stop"

        with client.messages.with_streaming_response.create(
            **_kwargs("stream_text"),
            stream=True,
        ) as response:
            streamed_response = response.parse()
            response_events = list(streamed_response)
            streamed_response.close()
        assert response_events[-1].type == "message_stop"

        with client.messages.stream(**_kwargs("stream_thinking")) as stream:
            message = stream.get_final_message()
        assert [block.type for block in message.content] == ["thinking", "text"]
        assert message.content[0].thinking == "Check both inputs."
        assert message.content[0].signature == "fixture-signature"
        assert message.content[1].text == "done"


@pytest.mark.asyncio
async def test_async_stream_parallel_tools() -> None:
    with FixtureServer() as server:
        async with anthropic.AsyncAnthropic(
            api_key="fixture-key",
            base_url=server.base_url,
            max_retries=0,
            timeout=10,
            _strict_response_validation=True,
        ) as client:
            async with client.messages.stream(
                **_kwargs("stream_parallel_tools")
            ) as stream:
                events = [event async for event in stream]
                message = await stream.get_final_message()
            raw_stream = await client.messages.create(
                **_kwargs("stream_parallel_tools"),
                stream=True,
            )
            raw_events = [event async for event in raw_stream]
            await raw_stream.close()
        calls = [block for block in message.content if block.type == "tool_use"]
        assert len(calls) == 2
        assert calls[0].input == {"city": "Paris", "unit": "c"}
        assert calls[1].input == {"city": "Tokyo", "unit": "c"}
        assert [event.type for event in events].count("content_block_start") == 2
        assert raw_events[-1].type == "message_stop"


def test_count_tokens_sync_async_and_raw() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        kwargs = {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Count this"}],
        }
        assert client.messages.count_tokens(**kwargs).input_tokens == 37
        raw = client.messages.with_raw_response.count_tokens(**kwargs)
        assert raw.request_id == "req_fixture_123"
        assert raw.parse().input_tokens == 37
        with client.messages.with_streaming_response.count_tokens(**kwargs) as response:
            assert response.parse().input_tokens == 37


class Weather(BaseModel):
    city: str
    temperature: int


def test_parse_helper_uses_messages_endpoint() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        message = client.messages.parse(
            **_kwargs("parse"),
            output_format=Weather,
        )
        block = message.content[0]
        assert block.type == "text"
        assert block.parsed_output == Weather(city="Paris", temperature=21)
        assert server.records[-1]["path"] == "/v1/messages"
        assert server.records[-1]["body"]["output_config"]["format"]["type"] == "json_schema"


def test_sdk_serializes_rich_1_3_request() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        client.messages.create(
            model=MODEL,
            max_tokens=128,
            messages=[
                {"role": "system", "content": "Inline policy"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Inspect both inputs"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "iVBORw0KGgo=",
                            },
                        },
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": "JVBERi0xLjQ=",
                            },
                        },
                    ],
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Need both tools",
                            "signature": "history-signature",
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_history",
                            "name": "get_weather",
                            "input": {"city": "Paris"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_history",
                            "content": "21 C",
                        }
                    ],
                },
            ],
            system=[
                {
                    "type": "text",
                    "text": "Top-level policy",
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
                }
            ],
            cache_control={"type": "ephemeral", "ttl": "5m"},
            container={"id": "container_fixture"},
            inference_geo="global",
            metadata={"user_id": "fixture-user"},
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {"type": "object", "properties": {}},
                },
            },
            service_tier="auto",
            stop_sequences=["STOP"],
            thinking={"type": "adaptive", "display": "summarized"},
            tool_choice={"type": "auto", "disable_parallel_tool_use": False},
            tools=[
                {
                    "type": "custom",
                    "name": "get_weather",
                    "description": "Return weather",
                    "input_schema": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                    "strict": True,
                    "eager_input_streaming": True,
                    "input_examples": [{"city": "Paris"}],
                }
            ],
            user_profile_id="profile_fixture",
        )
        record = server.records[-1]
        assert record["path"] == "/v1/messages"
        assert record["headers"]["anthropic-user-profile-id"] == "profile_fixture"
        assert record["body"]["messages"][0]["role"] == "system"
        assert record["body"]["thinking"]["type"] == "adaptive"
        assert record["body"]["tools"][0]["eager_input_streaming"] is True
        assert record["body"]["container"]["id"] == "container_fixture"


def test_anthropic_error_envelope_becomes_typed_exception() -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        with pytest.raises(anthropic.BadRequestError) as caught:
            client.messages.create(**_kwargs("error"))
        assert caught.value.status_code == 400
        assert caught.value.body["error"]["type"] == "invalid_request_error"
        assert "fixture rejected" in caught.value.message


@pytest.mark.parametrize(
    ("case", "block_types", "stop_reason", "stop_sequence"),
    [
        ("empty", ["text"], "end_turn", None),
        ("thinking", ["thinking", "text"], "end_turn", None),
        ("redacted", ["redacted_thinking", "text"], "end_turn", None),
        ("server_tool", ["server_tool_use"], "pause_turn", None),
        ("stop_sequence", ["text"], "stop_sequence", "HALT"),
        ("max_tokens", ["text"], "max_tokens", None),
        ("refusal", ["text"], "refusal", None),
        ("context_limit", ["text"], "model_context_window_exceeded", None),
    ],
)
def test_nonstream_response_union_and_stop_reasons(
    case: str,
    block_types: list[str],
    stop_reason: str,
    stop_sequence: str | None,
) -> None:
    with FixtureServer() as server:
        message = _client(server.base_url).messages.create(**_kwargs(case))
    assert [block.type for block in message.content] == block_types
    assert message.stop_reason == stop_reason
    assert message.stop_sequence == stop_sequence
    if case == "refusal":
        assert message.stop_details is not None
        assert message.stop_details.category == "cyber"
