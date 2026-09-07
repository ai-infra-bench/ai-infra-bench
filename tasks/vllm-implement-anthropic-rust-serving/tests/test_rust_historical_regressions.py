from __future__ import annotations

import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from verifier_support import RustServer, minimax_tool_call


MODEL = "local-model"
TOOL = {
    "type": "custom",
    "name": "get_weather",
    "description": "Return weather",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["city"],
    },
}


def sdk(base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="history-key",
        base_url=base_url,
        max_retries=0,
        timeout=20,
        _strict_response_validation=True,
    )


def kwargs(*, stream: bool | None = None) -> dict:
    result = {
        "model": MODEL,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "HISTORICAL_REGRESSION"}],
    }
    if stream is not None:
        result["stream"] = stream
    return result


def test_stream_message_start_has_required_type_and_role(tmp_path: Path) -> None:
    with RustServer(tmp_path, ["strict stream"], chunk_sizes=[1, 2]) as server:
        with httpx2.stream(
            "POST",
            f"{server.base_url}/v1/messages",
            headers={
                "content-type": "application/json",
                "x-api-key": "history-key",
                "anthropic-version": "2023-06-01",
            },
            json=kwargs(stream=True),
            timeout=20,
        ) as response:
            assert response.status_code == 200
            data_lines = [
                line for line in response.iter_lines() if line.startswith("data: ")
            ]
        first = json.loads(data_lines[0][len("data: ") :])
        assert first["type"] == "message_start"
        assert first["message"]["type"] == "message"
        assert first["message"]["role"] == "assistant"


def test_empty_nonstream_has_no_generated_content(tmp_path: Path) -> None:
    with RustServer(tmp_path, [""]) as server:
        message = sdk(server.base_url).messages.create(**kwargs())
    assert all(block.type == "text" and block.text == "" for block in message.content)
    assert message.stop_reason == "end_turn"
    assert message.usage.output_tokens == 0


def test_empty_stream_has_no_generated_content(tmp_path: Path) -> None:
    with RustServer(tmp_path, [""]) as server:
        with sdk(server.base_url).messages.stream(**kwargs()) as stream:
            events = list(stream)
            final = stream.get_final_message()
    assert events[0].type == "message_start"
    assert events[-1].type == "message_stop"
    assert all(block.type == "text" and block.text == "" for block in final.content)
    assert final.stop_reason == "end_turn"
    assert final.usage.output_tokens == 0


def mixed_output() -> str:
    return "PREFACE_SENTINEL\n" + minimax_tool_call(
        "get_weather",
        [("city", "Paris"), ("note", "TOOL_NOTE_SENTINEL")],
    )


def create_with_tool(base_url: str, *, stream: bool = False):
    return sdk(base_url).messages.create(
        model=MODEL,
        max_tokens=64,
        messages=[{"role": "user", "content": "Use the weather tool"}],
        tools=[TOOL],
        tool_choice={"type": "auto", "disable_parallel_tool_use": False},
        stream=stream,
    )


def assert_mixed_message(message) -> None:
    assert len(message.content) >= 2
    assert all(block.type == "text" for block in message.content[:-1])
    assert "PREFACE_SENTINEL" in "".join(block.text for block in message.content[:-1])
    assert message.content[-1].type == "tool_use"
    assert message.content[-1].name == "get_weather"
    assert message.content[-1].input == {
        "city": "Paris",
        "note": "TOOL_NOTE_SENTINEL",
    }
    assert message.stop_reason == "tool_use"


def test_combined_text_and_tool_nonstream(tmp_path: Path) -> None:
    with RustServer(tmp_path, [mixed_output()], tool_parser="minimax_m2") as server:
        assert_mixed_message(create_with_tool(server.base_url))


def test_combined_text_and_tool_stream(tmp_path: Path) -> None:
    with RustServer(
        tmp_path,
        [mixed_output()],
        tool_parser="minimax_m2",
        chunk_sizes=[1, 4, 2, 7],
    ) as server:
        with sdk(server.base_url).messages.stream(
            model=MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": "Use the weather tool"}],
            tools=[TOOL],
            tool_choice={"type": "auto", "disable_parallel_tool_use": False},
        ) as stream:
            final = stream.get_final_message()
    assert_mixed_message(final)


def test_streamed_arguments_equal_nonstream_without_duplication(tmp_path: Path) -> None:
    output = minimax_tool_call(
        "get_weather",
        [("city", "Reykjavik"), ("note", "exactly-once")],
    )
    nonstream_root = tmp_path / "nonstream"
    nonstream_root.mkdir()
    stream_root = tmp_path / "stream"
    stream_root.mkdir()
    with RustServer(nonstream_root, [output], tool_parser="minimax_m2") as server:
        complete = create_with_tool(server.base_url).content[0]
    with RustServer(
        stream_root,
        [output],
        tool_parser="minimax_m2",
        chunk_sizes=[1, 2, 3, 5],
    ) as server:
        with sdk(server.base_url).messages.stream(
            model=MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": "Use the weather tool"}],
            tools=[TOOL],
            tool_choice={"type": "auto"},
        ) as stream:
            streamed = stream.get_final_message().content[0]
    assert complete.type == "tool_use"
    assert streamed.type == "tool_use"
    assert (
        streamed.input
        == complete.input
        == {
            "city": "Reykjavik",
            "note": "exactly-once",
        }
    )


@pytest.mark.parametrize(
    "chunk_sizes",
    [
        [1] * 512,
        [1, 7, 2, 13, 3, 5] * 64,
        [19, 1, 1, 2, 31, 3] * 32,
    ],
    ids=["one-token", "mixed-small", "mixed-large"],
)
def test_tool_stream_chunk_boundaries_do_not_leak_markers(
    tmp_path: Path, chunk_sizes: list[int]
) -> None:
    output = minimax_tool_call(
        "get_weather",
        [("city", "Kyoto"), ("note", "boundary-sensitive")],
    )
    with RustServer(
        tmp_path,
        [output],
        tool_parser="minimax_m2",
        chunk_sizes=chunk_sizes,
    ) as server:
        with sdk(server.base_url).messages.stream(
            model=MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": "Use the weather tool"}],
            tools=[TOOL],
            tool_choice={"type": "auto"},
        ) as stream:
            events = list(stream)
            final = stream.get_final_message()
    calls = [block for block in final.content if block.type == "tool_use"]
    text = "".join(block.text for block in final.content if block.type == "text")
    assert len(calls) == 1
    assert calls[0].input["note"] == "boundary-sensitive"
    assert "minimax:tool_call" not in text
    assert "<invoke" not in text
    assert any(event.type == "content_block_delta" for event in events)
