"""Execute Python's production response converters, then parse with SDK 1.3.

The input is reconstructed OpenAI response/SSE data. This qualifies only the
Python Anthropic conversion stage, not its model parser or full serving path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import protocol_fixture
from vllm.entrypoints.anthropic.serving import AnthropicServingMessages
from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionResponse


def full_response(message: dict, *, finish="stop", stop_reason=None):
    return ChatCompletionResponse.model_validate(
        {
            "id": "chatcmpl_python_audit",
            "object": "chat.completion",
            "created": 1,
            "model": "local-model",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", **message},
                    "finish_reason": finish,
                    "stop_reason": stop_reason,
                }
            ],
            "usage": {
                "prompt_tokens": 23,
                "completion_tokens": 7,
                "total_tokens": 30,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        }
    )


def chunk(delta: dict, *, finish=None, stop_reason=None):
    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl_python_audit",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "local-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": finish,
                        "stop_reason": stop_reason,
                    }
                ],
                "usage": {
                    "prompt_tokens": 23,
                    "completion_tokens": 7,
                    "total_tokens": 30,
                    "prompt_tokens_details": {"cached_tokens": 3},
                },
            }
        )
        + "\n\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []

    # These converters do not need an engine/renderer. Supply only the state
    # that __init__ assigns for finish-reason conversion; no route logic is
    # replaced and no converted response is rewritten before SDK validation.
    converter = object.__new__(AnthropicServingMessages)
    converter.stop_reason_map = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
    }
    calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"city": city}),
            },
        }
        for i, city in enumerate(("Paris", "Tokyo"))
    ]
    cases = [
        ("empty_nonstream", full_response({"content": ""}), ["text"], "end_turn", None),
        (
            "thinking_text_nonstream",
            full_response({"reasoning": "reason", "content": "answer"}),
            ["thinking", "text"],
            "end_turn",
            None,
        ),
        (
            "mixed_text_tool_nonstream",
            full_response(
                {"content": "preface", "tool_calls": calls[:1]}, finish="tool_calls"
            ),
            ["text", "tool_use"],
            "tool_use",
            None,
        ),
        (
            "parallel_tools_nonstream",
            full_response({"content": None, "tool_calls": calls}, finish="tool_calls"),
            ["tool_use", "tool_use"],
            "tool_use",
            None,
        ),
        (
            "matched_stop_nonstream",
            full_response({"content": "visible"}, stop_reason="HALT"),
            ["text"],
            "stop_sequence",
            "HALT",
        ),
        (
            "max_tokens_nonstream",
            full_response({"content": "partial"}, finish="length"),
            ["text"],
            "max_tokens",
            None,
        ),
    ]

    def record(name, operation):
        row = {
            "case": name,
            "boundary": "production Python Anthropic converter -> fixture TCP HTTP/SSE -> official SDK; OpenAI-side input is reconstructed",
        }
        try:
            row.update(operation() or {})
            row["status"] = "passed"
        except Exception as error:
            row.update(
                status="incompatible",
                exception=type(error).__name__,
                detail=str(error)[:2000],
            )
        rows.append(row)

    def sdk(url):
        return anthropic.Anthropic(
            api_key="audit",
            base_url=url,
            max_retries=0,
            _strict_response_validation=True,
        )

    kwargs = {
        "model": "local-model",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "output audit"}],
    }
    for name, response, types, reason, sequence in cases:

        def probe(response=response, types=types, reason=reason, sequence=sequence):
            converted = converter.messages_full_converter(response).model_dump(
                exclude_none=True
            )
            protocol_fixture._message = lambda body, case: converted
            with protocol_fixture.FixtureServer() as server:
                result = sdk(server.base_url).messages.create(**kwargs)
            assert [block.type for block in result.content] == types
            assert result.stop_reason == reason, (
                f"actual stop_reason={result.stop_reason}, expected={reason}"
            )
            assert result.stop_sequence == sequence
            assert (
                result.usage.input_tokens == 20
                and result.usage.cache_read_input_tokens == 3
            )
            return {
                "stop_reason": result.stop_reason,
                "block_types": types,
                "cache_read_input_tokens": 3,
            }

        record(name, probe)

    streams = [
        (
            "text_stream_and_required_start_fields",
            [
                chunk({"role": "assistant", "content": ""}),
                chunk({"content": "hello"}),
                chunk({}, finish="stop"),
                "data: [DONE]\n\n",
            ],
            "end_turn",
            None,
            ["text"],
        ),
        (
            "empty_stream",
            [
                chunk({"role": "assistant", "content": ""}),
                chunk({}, finish="stop"),
                "data: [DONE]\n\n",
            ],
            "end_turn",
            None,
            None,
        ),
        (
            "matched_stop_stream",
            [
                chunk({"role": "assistant", "content": ""}),
                chunk({"content": "visible"}),
                chunk({}, finish="stop", stop_reason="HALT"),
                "data: [DONE]\n\n",
            ],
            "stop_sequence",
            "HALT",
            ["text"],
        ),
        (
            "max_tokens_stream",
            [
                chunk({"role": "assistant", "content": ""}),
                chunk({"content": "partial"}),
                chunk({}, finish="length"),
                "data: [DONE]\n\n",
            ],
            "max_tokens",
            None,
            ["text"],
        ),
    ]
    for name, source, reason, sequence, types in streams:

        def probe(source=source, reason=reason, sequence=sequence, types=types):
            async def collect():
                async def generated():
                    for value in source:
                        if value == "data: [DONE]\n\n":
                            usage = json.loads(chunk({})[6:])
                            usage["choices"] = []
                            if types is None:
                                usage["usage"]["completion_tokens"] = 0
                                usage["usage"]["total_tokens"] = 23
                            yield "data: " + json.dumps(usage) + "\n\n"
                        yield value

                return "".join(
                    [
                        value
                        async for value in converter.message_stream_converter(
                            generated()
                        )
                    ]
                ).encode()

            converted = asyncio.run(collect())
            protocol_fixture._stream = lambda body, case: converted
            with protocol_fixture.FixtureServer() as server:
                with sdk(server.base_url).messages.stream(**kwargs) as stream:
                    events = list(stream)
                    result = stream.get_final_message()
            assert (
                events[0].type == "message_start" and events[-1].type == "message_stop"
            )
            assert result.role == "assistant" and result.type == "message"
            if types is None:
                assert all(
                    block.type == "text" and block.text == ""
                    for block in result.content
                )
                assert result.usage.output_tokens == 0
            else:
                assert [block.type for block in result.content] == types, (
                    f"actual content={[block.model_dump() for block in result.content]}, expected block types={types}"
                )
            assert result.stop_reason == reason, (
                f"actual stop_reason={result.stop_reason}, expected={reason}"
            )
            assert result.stop_sequence == sequence
            return {
                "stop_reason": result.stop_reason,
                "block_types": [block.type for block in result.content],
            }

        record(name, probe)
    result = {
        "base_commit": "e196268bade5291c3fd80906bf9cd8c64851b21b",
        "sdk": "anthropic==1.3.0",
        "records": rows,
        "summary": {
            status: sum(row["status"] == status for row in rows)
            for status in ("passed", "incompatible")
        },
        "limitation": "Component evidence only. Passing reconstructed OpenAI-response inputs does not establish engine output parsing, tool JSON fragmentation, concurrency, or a complete Rust Oracle.",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
