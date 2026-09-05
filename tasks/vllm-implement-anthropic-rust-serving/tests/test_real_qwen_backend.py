"""Positive controls through Base's existing routes and the candidate's backend.

These execute the same real Rust renderer, tokenizer, engine transport, and
output processors as the Anthropic cases without requiring an Anthropic route.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import httpx2
import pytest

from verifier_support import (
    RustServer,
    assert_engine_token_ids,
    assert_json_constraint,
    reference_tokenizer,
)


@lru_cache(maxsize=1)
def template_reference():
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        "/opt/models/qwen-template", local_files_only=True
    )


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "user", "content": "Hello 世界 🍣"}],
        [
            {"role": "system", "content": "Keep the policy: café."},
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
            {"role": "user", "content": "Next question: 中文"},
        ],
    ],
    ids=["unicode", "system-history"],
)
def test_qwen_template_and_exact_prompt_ids(
    tmp_path: Path, messages: list[dict]
) -> None:
    with RustServer(tmp_path, ["Native reply 你好 🍣"]) as server:
        response = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={"model": "local-model", "messages": messages, "max_tokens": 64},
            timeout=20,
        )
        assert response.status_code == 200, response.text
        assert (
            response.json()["choices"][0]["message"]["content"]
            == "Native reply 你好 🍣"
        )
        capture = server.captures()[-1]
        expected = template_reference().apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
            preserve_thinking=True,
        )
        assert capture["prompt"] == expected
        assert_engine_token_ids(capture)
        assert response.json()["usage"]["prompt_tokens"] == len(
            capture["prompt_token_ids"]
        )
        tokenized = httpx2.post(
            f"{server.base_url}/tokenize",
            json={
                "model": "local-model",
                "messages": messages,
                "add_generation_prompt": True,
            },
            timeout=20,
        )
        assert tokenized.status_code == 200, tokenized.text
        assert tokenized.json()["tokens"] == capture["prompt_token_ids"]
        assert len(server.captures()) == 1


def test_qwen_tools_and_results_reach_rendered_prompt(tmp_path: Path) -> None:
    messages = [
        {"role": "user", "content": "Look up the value"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_lookup",
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": json.dumps({"key": "天气"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_lookup",
            "content": "TOOL_RESULT_NATIVE",
        },
    ]
    tool = {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "LOOKUP_NATIVE_TOOL",
            "parameters": {"type": "object", "properties": {"key": {"type": "string"}}},
        },
    }
    with RustServer(tmp_path, ["tool history accepted"]) as server:
        response = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": messages,
                "tools": [tool],
                "max_tokens": 64,
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        capture = server.captures()[-1]
        for text in (
            "<tools>",
            "LOOKUP_NATIVE_TOOL",
            "<function=lookup>",
            "天气",
            "<tool_response>",
            "TOOL_RESULT_NATIVE",
        ):
            assert text in capture["prompt"]
        assert_engine_token_ids(capture)


def test_qwen_stream_decodes_real_token_fragments(tmp_path: Path) -> None:
    output = '你好 München 🍣 quote " and slash \\'
    with RustServer(tmp_path, [output], chunk_sizes=[1] * 128) as server:
        with httpx2.stream(
            "POST",
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": [{"role": "user", "content": "Stream unicode"}],
                "max_tokens": 64,
                "stream": True,
            },
            timeout=20,
        ) as response:
            assert response.status_code == 200
            chunks = [
                json.loads(line[6:])
                for line in response.iter_lines()
                if line.startswith("data: ") and line != "data: [DONE]"
            ]
        text = "".join(
            choice["delta"].get("content") or ""
            for chunk in chunks
            for choice in chunk.get("choices", [])
        )
        assert text == output
        assert_engine_token_ids(server.captures()[-1])


def test_qwen_reasoning_uses_enabled_template(tmp_path: Path) -> None:
    output = "reasoning sentinel</think>answer sentinel"
    with RustServer(
        tmp_path,
        [output],
        reasoning_parser="qwen3",
        enable_thinking=True,
        chunk_sizes=[1, 2, 5, 3],
    ) as server:
        response = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": [{"role": "user", "content": "Think then answer"}],
                "max_tokens": 64,
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        message = response.json()["choices"][0]["message"]
        assert message["reasoning"] == "reasoning sentinel"
        assert message["content"] == "answer sentinel"
        capture = server.captures()[-1]
        assert capture["prompt"].endswith("<think>\n")
        assert_engine_token_ids(capture)


def test_qwen_structured_constraint_reaches_engine(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
        "additionalProperties": False,
    }
    with RustServer(tmp_path, ['{"answer":42}']) as server:
        response = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": [{"role": "user", "content": "Give an integer answer"}],
                "max_tokens": 64,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "answer", "schema": schema},
                },
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        assert json.loads(response.json()["choices"][0]["message"]["content"]) == {
            "answer": 42
        }
        assert_json_constraint(server.captures()[-1], schema)


@pytest.mark.parametrize("stop", ["FIRST_STOP", "SECOND_STOP"])
def test_qwen_stop_strings_are_processed_before_response(
    tmp_path: Path, stop: str
) -> None:
    with RustServer(
        tmp_path, [f"visible{stop}must not appear"], chunk_sizes=[1] * 128
    ) as server:
        response = httpx2.post(
            f"{server.base_url}/v1/chat/completions",
            json={
                "model": "local-model",
                "messages": [{"role": "user", "content": "Stop on either marker"}],
                "max_tokens": 64,
                "stop": ["FIRST_STOP", "SECOND_STOP"],
            },
            timeout=20,
        )
        assert response.status_code == 200, response.text
        assert response.json()["choices"][0]["message"]["content"] == "visible"


@pytest.mark.parametrize("endpoint", ["chat/completions", "completions"])
@pytest.mark.parametrize("streaming", [False, True], ids=["nonstream", "stream"])
@pytest.mark.parametrize(
    "options",
    [
        {"max_tokens": 3, "temperature": 0.17, "top_p": 0.73, "top_k": 7},
        {"max_tokens": 11, "temperature": 0.83, "top_p": 0.41, "top_k": 23},
    ],
    ids=["small-limit", "larger-limit"],
)
def test_native_generation_options_reach_engine(
    tmp_path: Path,
    endpoint: str,
    streaming: bool,
    options: dict,
) -> None:
    output = "amber cobalt linen violet silver cedar " * 16
    tokenizer = reference_tokenizer()
    tokens = tokenizer.encode(output, add_special_tokens=False).ids
    expected = tokenizer.decode(
        tokens[: options["max_tokens"]], skip_special_tokens=False
    )
    is_chat = endpoint == "chat/completions"
    request = {"model": "local-model", "stream": streaming, **options}
    if is_chat:
        request["messages"] = [
            {"role": "user", "content": "Respect the generation settings"}
        ]
    else:
        request["prompt"] = "Respect the generation settings"
    with RustServer(tmp_path, [output], chunk_sizes=[1, 4, 2]) as server:
        if streaming:
            with httpx2.stream(
                "POST", f"{server.base_url}/v1/{endpoint}", json=request, timeout=20
            ) as response:
                assert response.status_code == 200
                chunks = [
                    json.loads(line[6:])
                    for line in response.iter_lines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
            choices = [
                choice for chunk in chunks for choice in chunk.get("choices", [])
            ]
            text = "".join(
                (
                    choice.get("delta", {}).get("content")
                    if is_chat
                    else choice.get("text")
                )
                or ""
                for choice in choices
            )
            assert [c["finish_reason"] for c in choices if c.get("finish_reason")] == [
                "length"
            ]
        else:
            response = httpx2.post(
                f"{server.base_url}/v1/{endpoint}", json=request, timeout=20
            )
            assert response.status_code == 200, response.text
            body = response.json()
            choice = body["choices"][0]
            text = choice["message"]["content"] if is_chat else choice["text"]
            assert choice["finish_reason"] == "length"
            assert body["usage"]["completion_tokens"] == options["max_tokens"]
        assert text == expected
        captures = server.captures()
        assert len(captures) == 1
        received = captures[0]["sampling_params"]
        for name, value in options.items():
            assert received[name] == pytest.approx(value), {
                "field": name,
                "received": received,
            }


@pytest.mark.parametrize("streaming", [False, True], ids=["nonstream", "stream"])
def test_native_tool_none_preserves_text_without_tool_calls(
    tmp_path: Path, streaming: bool
) -> None:
    output = "Answer directly without using a tool."
    with RustServer(tmp_path, [output]) as server:
        request = {
            "model": "local-model",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": "Answer directly"}],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "unused_tool",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ],
            "tool_choice": "none",
            "stream": streaming,
        }
        if streaming:
            with httpx2.stream(
                "POST",
                f"{server.base_url}/v1/chat/completions",
                json=request,
                timeout=20,
            ) as response:
                assert response.status_code == 200
                chunks = [
                    json.loads(line[6:])
                    for line in response.iter_lines()
                    if line.startswith("data: ") and line != "data: [DONE]"
                ]
            deltas = [
                choice["delta"]
                for chunk in chunks
                for choice in chunk.get("choices", [])
            ]
            assert all(not delta.get("tool_calls") for delta in deltas)
            assert "".join(delta.get("content") or "" for delta in deltas) == output
        else:
            response = httpx2.post(
                f"{server.base_url}/v1/chat/completions", json=request, timeout=20
            )
            assert response.status_code == 200, response.text
            message = response.json()["choices"][0]["message"]
            assert not message.get("tool_calls")
            assert message["content"] == output
