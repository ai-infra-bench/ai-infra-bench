from __future__ import annotations

from typing import Any, Iterator

import anthropic
import pytest

from verifier_support import (
    RustServer,
    assert_count_matches_generation,
    assert_json_constraint,
)


MODEL = "local-model"


def sdk(base_url: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="matrix-key",
        base_url=base_url,
        max_retries=0,
        timeout=20,
        _strict_response_validation=True,
    )


def tool(**extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "custom",
        "name": "matrix_tool",
        "description": "MATRIX_TOOL_DESCRIPTION",
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    }
    value.update(extra)
    return value


BASE = {
    "model": MODEL,
    "max_tokens": 64,
    "messages": [{"role": "user", "content": "MATRIX_BASE_USER"}],
}


SUCCESS_CASES: list[tuple[str, dict[str, Any], tuple[str, ...]]] = [
    (
        "consecutive_user_messages",
        {
            "messages": [
                {"role": "user", "content": "CONSECUTIVE_USER_FIRST"},
                {"role": "user", "content": "CONSECUTIVE_USER_SECOND"},
            ]
        },
        ("CONSECUTIVE_USER_FIRST", "CONSECUTIVE_USER_SECOND"),
    ),
    (
        "consecutive_assistant_messages",
        {
            "messages": [
                {"role": "user", "content": "ASSISTANT_RUN_USER_FIRST"},
                {"role": "assistant", "content": "ASSISTANT_RUN_FIRST"},
                {"role": "assistant", "content": "ASSISTANT_RUN_SECOND"},
                {"role": "user", "content": "ASSISTANT_RUN_USER_LAST"},
            ]
        },
        ("ASSISTANT_RUN_FIRST", "ASSISTANT_RUN_SECOND", "ASSISTANT_RUN_USER_LAST"),
    ),
    (
        "multiple_text_blocks",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "MULTI_TEXT_FIRST"},
                        {
                            "type": "text",
                            "text": "MULTI_TEXT_SECOND",
                            "cache_control": {"type": "ephemeral", "ttl": "5m"},
                        },
                    ],
                }
            ]
        },
        ("MULTI_TEXT_FIRST", "MULTI_TEXT_SECOND"),
    ),
    (
        "multiple_top_system_blocks",
        {
            "system": [
                {"type": "text", "text": "MULTI_TOP_SYSTEM_FIRST"},
                {
                    "type": "text",
                    "text": "MULTI_TOP_SYSTEM_SECOND",
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
                },
            ],
            "messages": [{"role": "user", "content": "MULTI_TOP_SYSTEM_USER"}],
        },
        (
            "MULTI_TOP_SYSTEM_FIRST",
            "MULTI_TOP_SYSTEM_SECOND",
            "MULTI_TOP_SYSTEM_USER",
        ),
    ),
    (
        "top_system_string",
        {"system": "TOP_SYSTEM_STRING_SENTINEL"},
        ("TOP_SYSTEM_STRING_SENTINEL",),
    ),
    (
        "top_system_blocks",
        {
            "system": [
                {
                    "type": "text",
                    "text": "TOP_SYSTEM_BLOCK_SENTINEL",
                }
            ]
        },
        ("TOP_SYSTEM_BLOCK_SENTINEL",),
    ),
    (
        "leading_inline_system",
        {
            "messages": [
                {"role": "system", "content": "LEADING_INLINE_SYSTEM_SENTINEL"},
                {"role": "user", "content": "INLINE_USER_SENTINEL"},
            ]
        },
        ("LEADING_INLINE_SYSTEM_SENTINEL", "INLINE_USER_SENTINEL"),
    ),
    (
        "mid_conversation_system",
        {
            "messages": [
                {"role": "user", "content": "MID_SYSTEM_USER_ONE"},
                {"role": "assistant", "content": "MID_SYSTEM_ASSISTANT"},
                {"role": "system", "content": "MID_SYSTEM_POLICY"},
                {"role": "user", "content": "MID_SYSTEM_USER_TWO"},
            ]
        },
        (
            "MID_SYSTEM_USER_ONE",
            "MID_SYSTEM_ASSISTANT",
            "MID_SYSTEM_POLICY",
            "MID_SYSTEM_USER_TWO",
        ),
    ),
    (
        "multiple_inline_system",
        {
            "messages": [
                {"role": "system", "content": "MULTI_SYSTEM_ONE"},
                {"role": "user", "content": "MULTI_SYSTEM_USER"},
                {"role": "system", "content": "MULTI_SYSTEM_TWO"},
                {"role": "user", "content": "MULTI_SYSTEM_FINAL"},
            ]
        },
        ("MULTI_SYSTEM_ONE", "MULTI_SYSTEM_TWO", "MULTI_SYSTEM_FINAL"),
    ),
    (
        "assistant_text_prefill",
        {
            "messages": [
                {"role": "user", "content": "PREFILL_USER"},
                {"role": "assistant", "content": "PREFILL_ASSISTANT"},
            ]
        },
        ("PREFILL_USER", "PREFILL_ASSISTANT"),
    ),
    (
        "assistant_thinking_and_text",
        {
            "messages": [
                {"role": "user", "content": "THINKING_HISTORY_USER"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "THINKING_HISTORY_REASON",
                            "signature": "history-signature",
                        },
                        {"type": "text", "text": "THINKING_HISTORY_TEXT"},
                    ],
                },
                {"role": "user", "content": "THINKING_HISTORY_FINAL"},
            ]
        },
        ("THINKING_HISTORY_REASON", "THINKING_HISTORY_TEXT", "THINKING_HISTORY_FINAL"),
    ),
    (
        "assistant_redacted_thinking",
        {
            "messages": [
                {"role": "user", "content": "REDACTED_USER"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "redacted_thinking", "data": "OPAQUE_REDACTED_DATA"},
                        {"type": "text", "text": "REDACTED_VISIBLE_TEXT"},
                    ],
                },
                {"role": "user", "content": "REDACTED_FINAL"},
            ]
        },
        ("REDACTED_VISIBLE_TEXT", "REDACTED_FINAL"),
    ),
    (
        "assistant_tool_use_history",
        {
            "messages": [
                {"role": "user", "content": "TOOL_HISTORY_USER"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "TOOL_HISTORY_TEXT"},
                        {
                            "type": "tool_use",
                            "id": "toolu_matrix_history",
                            "name": "matrix_tool",
                            "input": {"value": "TOOL_HISTORY_VALUE"},
                        },
                    ],
                },
                {"role": "user", "content": "TOOL_HISTORY_FINAL"},
            ]
        },
        ("TOOL_HISTORY_TEXT", "matrix_tool", "TOOL_HISTORY_VALUE"),
    ),
    (
        "tool_result_string",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_result_string",
                            "name": "matrix_tool",
                            "input": {"value": "x"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_result_string",
                            "content": "TOOL_RESULT_STRING_SENTINEL",
                        }
                    ],
                },
            ]
        },
        ("TOOL_RESULT_STRING_SENTINEL",),
    ),
    (
        "tool_result_text_blocks",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_result_blocks",
                            "name": "matrix_tool",
                            "input": {"value": "x"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_result_blocks",
                            "content": [
                                {"type": "text", "text": "TOOL_RESULT_BLOCK_ONE"},
                                {"type": "text", "text": "TOOL_RESULT_BLOCK_TWO"},
                            ],
                        }
                    ],
                },
            ]
        },
        ("TOOL_RESULT_BLOCK_ONE", "TOOL_RESULT_BLOCK_TWO"),
    ),
    (
        "tool_result_error",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_result_error",
                            "name": "matrix_tool",
                            "input": {"value": "x"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_result_error",
                            "content": "TOOL_RESULT_ERROR_SENTINEL",
                            "is_error": True,
                        }
                    ],
                },
            ]
        },
        ("TOOL_RESULT_ERROR_SENTINEL",),
    ),
    (
        "multiple_tool_results",
        {
            "messages": [
                {"role": "user", "content": "MULTI_TOOL_RESULTS_START"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_result_one",
                            "name": "matrix_tool_one",
                            "input": {"value": "one"},
                        },
                        {
                            "type": "tool_use",
                            "id": "toolu_result_two",
                            "name": "matrix_tool_two",
                            "input": {"value": "two"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_result_one",
                            "content": "MULTI_TOOL_RESULT_ONE",
                        },
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_result_two",
                            "content": [
                                {"type": "text", "text": "MULTI_TOOL_RESULT_TWO"}
                            ],
                        },
                    ],
                },
            ]
        },
        (
            "matrix_tool_one",
            "matrix_tool_two",
            "MULTI_TOOL_RESULT_ONE",
            "MULTI_TOOL_RESULT_TWO",
        ),
    ),
    (
        "long_multiturn",
        {
            "messages": [
                {
                    "role": "user" if index % 2 == 0 else "assistant",
                    "content": f"LONG_TURN_{index}_SENTINEL",
                }
                for index in range(12)
            ]
            + [{"role": "user", "content": "LONG_FINAL_SENTINEL"}]
        },
        ("LONG_TURN_0_SENTINEL", "LONG_TURN_11_SENTINEL", "LONG_FINAL_SENTINEL"),
    ),
    (
        "metadata_user_id",
        {
            "metadata": {"user_id": "matrix-user"},
        },
        ("MATRIX_BASE_USER",),
    ),
    (
        "output_effort",
        {
            "output_config": {"effort": "high"},
        },
        ("MATRIX_BASE_USER",),
    ),
    (
        "json_schema_output",
        {
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                    },
                }
            }
        },
        ("MATRIX_BASE_USER",),
    ),
    (
        "custom_tool_definition",
        {
            "tools": [
                tool(
                    strict=True,
                )
            ],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": False},
        },
        ("matrix_tool", "MATRIX_TOOL_DESCRIPTION"),
    ),
    (
        "multiple_stop_sequences",
        {"stop_sequences": ["STOP_ONE_SENTINEL", "STOP_TWO_SENTINEL"]},
        ("MATRIX_BASE_USER",),
    ),
]

# The real Qwen template requires a user query before assistant/tool history.
# Supply that conversation context rather than relying on a JSON renderer that
# accepts any role sequence. Keep all original blocks and sentinel assertions.
for _case_name, _overrides, _sentinels in SUCCESS_CASES:
    _messages = _overrides.get("messages", [])
    if _messages and _messages[0]["role"] == "assistant":
        _messages.insert(0, {"role": "user", "content": "Start the requested task."})


ORDERED_BLOCK_CASES = {
    "consecutive_user_messages",
    "consecutive_assistant_messages",
    "multiple_text_blocks",
    "multiple_top_system_blocks",
    "multiple_tool_results",
}


@pytest.fixture(scope="module")
def shared_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RustServer]:
    root = tmp_path_factory.mktemp("rust-request-matrix")
    with RustServer(root, ["matrix accepted"]) as server:
        yield server


@pytest.mark.parametrize(
    ("case_name", "overrides", "sentinels"),
    SUCCESS_CASES,
    ids=[case[0] for case in SUCCESS_CASES],
)
def test_request_variant_reaches_rust_semantic_path(
    shared_server: RustServer,
    case_name: str,
    overrides: dict[str, Any],
    sentinels: tuple[str, ...],
) -> None:
    before = len(shared_server.captures())
    kwargs = dict(BASE)
    kwargs.update(overrides)
    message = sdk(shared_server.base_url).messages.create(**kwargs)
    assert message.role == "assistant", case_name
    captures = shared_server.captures()
    assert len(captures) == before + 1, case_name
    prompt = captures[-1]["prompt"]
    for sentinel in sentinels:
        assert sentinel in prompt, {"case": case_name, "prompt": prompt}
    if case_name in ORDERED_BLOCK_CASES:
        positions = [prompt.index(sentinel) for sentinel in sentinels]
        assert positions == sorted(positions), {
            "case": case_name,
            "sentinels": sentinels,
            "positions": positions,
            "prompt": prompt,
        }
    if case_name == "json_schema_output":
        assert_json_constraint(
            captures[-1], overrides["output_config"]["format"]["schema"]
        )
    elif case_name == "output_effort":
        rendered = shared_server.render_captures()[-1]
        assert rendered["template_kwargs"]["reasoning_effort"] == "high"


COUNT_CASES: list[tuple[str, dict[str, Any]]] = [
    ("plain", {}),
    ("system", {"system": "COUNT_SYSTEM_SENTINEL"}),
    ("tools", {"tools": [tool()]}),
    ("thinking", {"thinking": {"type": "adaptive"}}),
    (
        "structured_output",
        {
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                        "required": ["answer"],
                    },
                }
            }
        },
    ),
    (
        "tool_choice",
        {
            "tools": [tool()],
            "tool_choice": {"type": "any", "disable_parallel_tool_use": True},
        },
    ),
    ("cache_control", {"cache_control": {"type": "ephemeral", "ttl": "5m"}}),
]


@pytest.mark.parametrize(
    ("case_name", "extra"), COUNT_CASES, ids=[case[0] for case in COUNT_CASES]
)
def test_count_tokens_request_variants(
    shared_server: RustServer,
    case_name: str,
    extra: dict[str, Any],
) -> None:
    assert_count_matches_generation(
        sdk(shared_server.base_url),
        shared_server,
        model=MODEL,
        messages=[{"role": "user", "content": f"COUNT_{case_name}"}],
        **extra,
    )
