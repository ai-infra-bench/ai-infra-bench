from __future__ import annotations

from unicode_fixture import (
    GlmDelegatingParser,
    QwenDelegatingParser,
    korean_tokens,
    parse,
)


def test_glm_korean_transition_preserves_unicode() -> None:
    output = parse(GlmDelegatingParser, korean_tokens(), {200}, 1)
    assert output.reasoning == "Let me think"
    assert output.content == "삼성전자의 주가입니다."


def test_qwen_korean_transition_preserves_unicode() -> None:
    output = parse(QwenDelegatingParser, korean_tokens(), {200}, 1)
    assert output.content == "삼성전자의 주가입니다."


def test_chunk_size_two_preserves_unicode_for_both_parsers() -> None:
    results = [
        parse(parser, korean_tokens(), {200}, 2)
        for parser in (GlmDelegatingParser, QwenDelegatingParser)
    ]
    assert [result.content for result in results] == [
        "삼성전자의 주가입니다.",
        "삼성전자의 주가입니다.",
    ]


def test_single_batch_transition_preserves_unicode_for_both_parsers() -> None:
    results = [
        parse(parser, korean_tokens(), {200}, None)
        for parser in (GlmDelegatingParser, QwenDelegatingParser)
    ]
    assert all("�" not in result.content for result in results)
    assert all(result.content == "삼성전자의 주가입니다." for result in results)


def test_consecutive_byte_fallback_tokens_are_not_deleted() -> None:
    tokens = [(100, "Reasoning"), (51, "</think>"), (200, "杭"), (201, "州"), (202, "天气")]
    output = parse(GlmDelegatingParser, tokens, {200, 201}, 1)
    assert output.content == "杭州天气"


def test_emoji_bytes_at_transition_are_preserved() -> None:
    tokens = [(100, "Reasoning"), (51, "</think>"), (210, "🧭"), (211, " route")]
    output = parse(QwenDelegatingParser, tokens, {210}, 1)
    assert output.content == "🧭 route"


def test_ascii_transition_remains_unchanged() -> None:
    tokens = [(100, "Reasoning"), (51, "</think>"), (220, "plain"), (221, " text")]
    output = parse(GlmDelegatingParser, tokens, set(), 1)
    assert output.reasoning == "Reasoning"
    assert output.content == "plain text"


def test_reasoning_only_finish_remains_reasoning() -> None:
    tokens = [(100, "still"), (101, " thinking")]
    output = parse(GlmDelegatingParser, tokens, set(), 1)
    assert output.reasoning == "still thinking"
    assert output.content == ""


def test_empty_content_after_transition_does_not_emit_replacement() -> None:
    tokens = [(100, "done"), (51, "</think>")]
    output = parse(QwenDelegatingParser, tokens, set(), 1)
    assert output.reasoning == "done"
    assert output.content == ""


def test_deferred_whitespace_at_transition_is_flushed() -> None:
    tokens = [
        (100, "Reasoning"),
        (101, " continues"),
        (51, "</think>"),
        (220, " "),
        (221, "answer"),
    ]
    results = [
        parse(parser, tokens, set(), 2)
        for parser in (GlmDelegatingParser, QwenDelegatingParser)
    ]
    assert [result.content for result in results] == [" answer", " answer"]


def test_unicode_content_with_tools_enabled_stays_content() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "lookup a value",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    results = [
        parse(parser, korean_tokens(), {200}, 2, tools=tools)
        for parser in (GlmDelegatingParser, QwenDelegatingParser)
    ]
    assert [result.content for result in results] == [
        "삼성전자의 주가입니다.",
        "삼성전자의 주가입니다.",
    ]
    assert all(not result.tool_names and not result.tool_arguments for result in results)


def test_chunk_size_matrix_is_invariant() -> None:
    observations = []
    for parser in (GlmDelegatingParser, QwenDelegatingParser):
        for chunk_size in (1, 2, 3, None):
            result = parse(parser, korean_tokens(), {200}, chunk_size)
            observations.append((result.reasoning, result.content))
    assert observations == [("Let me think", "삼성전자의 주가입니다.")] * 8
