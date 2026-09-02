from __future__ import annotations

import json

import pytest

from vllm.entrypoints.openai.engine.protocol import DeltaMessage

from kimi_output_mock import (
    BASH_TOOL_CHUNKS,
    EXPECTED_BASH_ARGUMENTS,
    PARALLEL_BASH_ARGUMENTS,
    PARALLEL_TOOL_CHUNKS,
    kimi_tool_chunks,
    separated_kimi_tool_chunks,
)
from verifier_support import (
    argument_deltas,
    build_kimi_serving,
    collect_events,
    collect_kimi_events,
    collect_nonstream_text,
    completed_calls,
)


def compact_json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@pytest.mark.asyncio
async def test_single_bash_command_is_complete() -> None:
    expected = compact_json(EXPECTED_BASH_ARGUMENTS)
    events = await collect_kimi_events(BASH_TOOL_CHUNKS)
    calls = completed_calls(events)
    assert len(calls) == 1
    assert calls[0]["name"] == "bash"
    assert calls[0]["arguments"] == expected
    assert "".join(argument_deltas(events)) == expected


@pytest.mark.asyncio
async def test_text_and_bash_command_both_reach_client() -> None:
    content = "I will inspect the failing path."
    arguments = {"command": "cd /testbed && sed -n '220,280p' astropy/modeling/separable.py"}
    chunks = kimi_tool_chunks(
        "bash",
        0,
        arguments,
        width=256,
        leading_content=content,
    )
    events = await collect_kimi_events(chunks)
    text = [
        event["delta"]
        for event in events
        if event["type"] == "response.output_text.delta"
    ]
    calls = completed_calls(events)
    assert text == [content]
    assert len(calls) == 1
    assert calls[0]["name"] == "bash"
    assert calls[0]["arguments"] == compact_json(arguments)


@pytest.mark.asyncio
async def test_parallel_bash_commands_remain_separate() -> None:
    events = await collect_kimi_events(PARALLEL_TOOL_CHUNKS)
    calls = completed_calls(events)
    assert len(calls) == 2
    assert [call["name"] for call in calls] == ["bash", "bash"]
    assert [json.loads(call["arguments"]) for call in calls] == PARALLEL_BASH_ARGUMENTS


@pytest.mark.asyncio
async def test_unicode_and_escaped_bash_command_is_exact() -> None:
    arguments = {
        "command": "printf '%s\\n' '서울 café 🚀' > /tmp/report.txt && printf '\"done\"'"
    }
    expected = compact_json(arguments)
    events = await collect_kimi_events(
        kimi_tool_chunks("bash", 0, arguments, width=37)
    )
    calls = completed_calls(events)
    assert len(calls) == 1
    assert calls[0]["arguments"] == expected
    assert "".join(argument_deltas(events)) == expected


@pytest.mark.asyncio
async def test_separately_delivered_name_and_arguments_still_work() -> None:
    arguments = {"command": "cd /testbed && git status --short"}
    expected = compact_json(arguments)
    events = await collect_kimi_events(
        separated_kimi_tool_chunks("bash", 0, expected)
    )
    calls = completed_calls(events)
    assert len(calls) == 1
    assert calls[0]["name"] == "bash"
    assert calls[0]["arguments"] == expected
    assert argument_deltas(events) == [expected]


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
async def test_nonstream_text_response_is_unchanged() -> None:
    response = await collect_nonstream_text("finished answer")
    assert response["status"] == "completed"
    assert response["output"][0]["content"][0]["text"] == "finished answer"


@pytest.mark.asyncio
async def test_malformed_bash_arguments_are_not_repaired() -> None:
    malformed = '{"command":"echo incomplete"'
    events = await collect_kimi_events(
        separated_kimi_tool_chunks("bash", 0, malformed)
    )
    calls = completed_calls(events)
    assert len(calls) == 1
    assert calls[0]["arguments"] == malformed
    with pytest.raises(json.JSONDecodeError):
        json.loads(calls[0]["arguments"])


@pytest.mark.asyncio
async def test_repeated_requests_do_not_share_stream_state() -> None:
    arguments = {"command": "cd /testbed && git diff --check"}
    expected = compact_json(arguments)
    chunks = separated_kimi_tool_chunks("bash", 0, expected)
    serving = build_kimi_serving(chunks)
    first = await collect_kimi_events(chunks, serving=serving)
    second = await collect_kimi_events(chunks, serving=serving)
    for events in (first, second):
        calls = completed_calls(events)
        assert len(calls) == 1
        assert calls[0]["name"] == "bash"
        assert calls[0]["arguments"] == expected
