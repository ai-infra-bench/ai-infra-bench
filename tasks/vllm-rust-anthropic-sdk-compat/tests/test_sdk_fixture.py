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
        assert message.usage.input_tokens == 19
        assert message.usage.output_tokens == 7
        assert message.usage.cache_creation_input_tokens == 3
        assert message.usage.cache_read_input_tokens == 5

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
        assert message.usage.input_tokens == 23
        assert message.usage.output_tokens == 4
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
        assert (
            server.records[-1]["body"]["output_config"]["format"]["type"]
            == "json_schema"
        )


def test_sdk_serializes_supported_request() -> None:
    with FixtureServer() as server:
        _client(server.base_url).messages.create(
            model=MODEL,
            max_tokens=128,
            system=[{"type": "text", "text": "Top-level policy"}],
            messages=[
                {"role": "system", "content": "Inline policy"},
                {"role": "user", "content": "Check the weather"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Need a tool",
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
            metadata={"user_id": "fixture-user"},
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {"type": "object", "properties": {}},
                },
            },
            stop_sequences=["STOP"],
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
                }
            ],
        )
        record = server.records[-1]
        assert record["path"] == "/v1/messages"
        assert record["headers"]["x-api-key"] == "fixture-key"
        assert record["headers"]["anthropic-version"] == "2023-06-01"
        assert record["body"]["messages"][0]["role"] == "system"
        assert record["body"]["tools"][0]["strict"] is True
        assert record["body"]["output_config"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize(
    ("case", "exception_type", "status", "error_type"),
    [
        ("error_400", anthropic.BadRequestError, 400, "invalid_request_error"),
        ("error_401", anthropic.AuthenticationError, 401, "authentication_error"),
        ("error_404", anthropic.NotFoundError, 404, "not_found_error"),
        ("error_500", anthropic.InternalServerError, 500, "api_error"),
    ],
)
def test_anthropic_error_envelope_becomes_typed_exception(
    case: str,
    exception_type: type[anthropic.APIStatusError],
    status: int,
    error_type: str,
) -> None:
    with FixtureServer() as server:
        client = _client(server.base_url)
        with pytest.raises(exception_type) as caught:
            client.messages.create(**_kwargs(case))
        assert caught.value.status_code == status
        assert caught.value.body["error"]["type"] == error_type
        assert caught.value.request_id == "req_fixture_123"
        assert "fixture" in caught.value.message


@pytest.mark.parametrize(
    ("case", "block_types", "stop_reason", "stop_sequence"),
    [
        ("empty", ["text"], "end_turn", None),
        ("thinking", ["thinking", "text"], "end_turn", None),
        ("stop_sequence", ["text"], "stop_sequence", "HALT"),
        ("max_tokens", ["text"], "max_tokens", None),
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


def test_stream_ping_is_ignored_without_changing_accumulation() -> None:
    with FixtureServer() as server:
        with _client(server.base_url).messages.stream(
            **_kwargs("stream_ping")
        ) as stream:
            events = list(stream)
            message = stream.get_final_message()
    assert message.content[0].text == "fixture stream"
    event_types = [event.type for event in events]
    assert "ping" not in event_types
    assert event_types[0] == "message_start"
    assert event_types[-1] == "message_stop"
    assert event_types.count("content_block_delta") == 2


def test_stream_error_event_becomes_sdk_exception() -> None:
    with FixtureServer() as server:
        stream = _client(server.base_url).messages.create(
            **_kwargs("stream_error"), stream=True
        )
        first = next(stream)
        assert first.type == "message_start"
        with pytest.raises(anthropic.APIStatusError) as caught:
            list(stream)
    assert caught.value.status_code == 200
    assert caught.value.body["type"] == "error"
    assert caught.value.body["error"]["type"] == "api_error"
    assert caught.value.request_id == "req_fixture_123"


@pytest.mark.parametrize(
    ("case", "stop_reason", "stop_sequence"),
    [
        ("stream_stop_sequence", "stop_sequence", "HALT"),
        ("stream_max_tokens", "max_tokens", None),
    ],
)
def test_stream_terminal_reason_and_sequence(
    case: str, stop_reason: str, stop_sequence: str | None
) -> None:
    with FixtureServer() as server:
        with _client(server.base_url).messages.stream(**_kwargs(case)) as stream:
            message = stream.get_final_message()
    assert message.stop_reason == stop_reason
    assert message.stop_sequence == stop_sequence
    assert message.usage.output_tokens == 4


def test_stream_fragmented_unicode_and_escaped_tool_json() -> None:
    with FixtureServer() as server:
        with _client(server.base_url).messages.stream(
            **_kwargs("stream_unicode_tool")
        ) as stream:
            events = list(stream)
            message = stream.get_final_message()
    assert message.stop_reason == "tool_use"
    assert len(message.content) == 1
    tool = message.content[0]
    assert tool.type == "tool_use"
    assert tool.input == {
        "city": "München",
        "note": 'quote " slash \\ emoji 🍣',
    }
    deltas = [
        event.delta.partial_json
        for event in events
        if event.type == "content_block_delta"
        and event.delta.type == "input_json_delta"
    ]
    assert len(deltas) >= 5
