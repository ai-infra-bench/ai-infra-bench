from __future__ import annotations

import json

import pytest

from vllm.entrypoints.openai.engine.protocol import (
    DeltaFunctionCall,
    DeltaMessage,
    DeltaToolCall,
)

from verifier_support import (
    argument_deltas,
    collect_events,
    collect_nonstream_text,
    completed_calls,
    responses_request,
)


def tool(
    index: int,
    *,
    name: str | None = None,
    arguments: str | None = None,
    call_id: str | None = None,
) -> DeltaToolCall:
    return DeltaToolCall(
        index=index,
        id=call_id,
        type="function" if call_id else None,
        function=DeltaFunctionCall(name=name, arguments=arguments),
    )


@pytest.mark.asyncio
async def test_name_and_first_arguments_in_one_delta() -> None:
    payload = '{"path":"/tmp/x.py","content":"print(1)"}'
    events = await collect_events(
        [DeltaMessage(tool_calls=[tool(0, name="write"), tool(0, arguments=payload)])]
    )
    assert argument_deltas(events) == [payload]
    assert completed_calls(events)[0]["arguments"] == payload
    assert json.loads(completed_calls(events)[0]["arguments"])["path"] == "/tmp/x.py"


@pytest.mark.asyncio
async def test_all_argument_fragments_from_same_model_step() -> None:
    fragments = ['{"path":', '"/srv/app.py",', '"content":"ok"}']
    events = await collect_events(
        [
            DeltaMessage(
                tool_calls=[
                    tool(0, name="write"),
                    *(tool(0, arguments=value) for value in fragments),
                ]
            )
        ]
    )
    assert "".join(argument_deltas(events)) == "".join(fragments)
    assert json.loads(completed_calls(events)[0]["arguments"])["content"] == "ok"


@pytest.mark.asyncio
async def test_content_and_tool_update_keep_event_order() -> None:
    payload = '{"query":"active incident"}'
    events = await collect_events(
        [
            DeltaMessage(
                content="I will check.",
                tool_calls=[
                    tool(0, name="search"),
                    tool(0, arguments=payload),
                ],
            )
        ],
        responses_request(tools=["search"]),
    )
    types = [event["type"] for event in events]
    assert "response.output_text.delta" in types
    assert types.index("response.output_text.delta") < types.index(
        "response.function_call_arguments.delta"
    )
    assert json.loads(completed_calls(events)[0]["arguments"])["query"]


@pytest.mark.asyncio
async def test_reasoning_content_and_tool_update_are_all_preserved() -> None:
    events = await collect_events(
        [
            DeltaMessage(
                reasoning="Checking the request.",
                content="I will use the tool.",
                tool_calls=[
                    tool(0, name="write"),
                    tool(0, arguments='{"path":"/tmp/y","content":"y"}'),
                ],
            )
        ]
    )
    types = [event["type"] for event in events]
    assert "response.reasoning_text.delta" in types
    assert "response.output_text.delta" in types
    assert "response.function_call_arguments.delta" in types
    assert types.index("response.reasoning_text.delta") < types.index(
        "response.output_text.delta"
    ) < types.index("response.function_call_arguments.delta")


@pytest.mark.asyncio
async def test_parallel_tools_in_one_delta_do_not_mix_arguments() -> None:
    events = await collect_events(
        [
            DeltaMessage(
                tool_calls=[
                    tool(0, name="write", arguments='{"path":"a","content":"A"}'),
                    tool(1, name="search", arguments='{"query":"B"}'),
                ]
            )
        ],
        responses_request(tools=["write", "search"]),
    )
    calls = completed_calls(events)
    assert [call["name"] for call in calls] == ["write", "search"]
    assert [json.loads(call["arguments"]) for call in calls] == [
        {"path": "a", "content": "A"},
        {"query": "B"},
    ]


@pytest.mark.asyncio
async def test_unicode_and_escaped_arguments_are_byte_exact() -> None:
    payload = '{"path":"/tmp/报告.json","content":"line\\n\\\"quoted\\\""}'
    events = await collect_events(
        [DeltaMessage(tool_calls=[tool(0, name="write"), tool(0, arguments=payload)])]
    )
    assert "".join(argument_deltas(events)) == payload
    assert completed_calls(events)[0]["arguments"] == payload


@pytest.mark.asyncio
async def test_separate_name_and_argument_deltas_still_work() -> None:
    payload = '{"path":"/tmp/z","content":"z"}'
    events = await collect_events(
        [
            DeltaMessage(tool_calls=[tool(0, name="write", call_id="call-z")]),
            DeltaMessage(tool_calls=[tool(0, arguments=payload)]),
        ]
    )
    assert argument_deltas(events) == [payload]
    assert completed_calls(events)[0]["arguments"] == payload


@pytest.mark.asyncio
async def test_plain_text_stream_is_unchanged() -> None:
    events = await collect_events(
        [DeltaMessage(content="alpha"), DeltaMessage(content=" beta")]
    )
    text = [
        event["delta"]
        for event in events
        if event["type"] == "response.output_text.delta"
    ]
    assert text == ["alpha", " beta"]
    assert completed_calls(events) == []


@pytest.mark.asyncio
async def test_reasoning_only_stream_is_unchanged() -> None:
    events = await collect_events(
        [DeltaMessage(reasoning="step one"), DeltaMessage(reasoning=" step two")]
    )
    reasoning = [
        event["delta"]
        for event in events
        if event["type"] == "response.reasoning_text.delta"
    ]
    assert reasoning == ["step one", " step two"]
    assert completed_calls(events) == []


@pytest.mark.asyncio
async def test_empty_tool_open_does_not_duplicate_items() -> None:
    payload = '{"path":"/tmp/a","content":"a"}'
    events = await collect_events(
        [
            DeltaMessage(tool_calls=[tool(0, name="write")]),
            DeltaMessage(tool_calls=[tool(0, arguments=payload)]),
        ]
    )
    added = [
        event
        for event in events
        if event["type"] == "response.output_item.added"
        and event["item"]["type"] == "function_call"
    ]
    assert len(added) == 1
    assert len(completed_calls(events)) == 1


@pytest.mark.asyncio
async def test_nonstream_text_response_is_unchanged() -> None:
    response = await collect_nonstream_text("finished answer")
    assert response["status"] == "completed"
    assert response["output"][0]["content"][0]["text"] == "finished answer"
