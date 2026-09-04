from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import anthropic
import httpx2
import pytest

from verifier_support import RustServer


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
        "top_system_string",
        {"system": "TOP_SYSTEM_STRING_SENTINEL"},
        ("TOP_SYSTEM_STRING_SENTINEL",),
    ),
    (
        "top_system_blocks_cache",
        {
            "system": [
                {
                    "type": "text",
                    "text": "TOP_SYSTEM_BLOCK_SENTINEL",
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
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
        "tool_result_tool_reference",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_reference",
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
                            "tool_use_id": "toolu_reference",
                            "content": [
                                {
                                    "type": "tool_reference",
                                    "tool_name": "TOOL_REFERENCE_SENTINEL",
                                }
                            ],
                        }
                    ],
                },
            ]
        },
        ("TOOL_REFERENCE_SENTINEL",),
    ),
    (
        "search_result_input",
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "search_result",
                            "source": "https://example.invalid/search",
                            "title": "SEARCH_RESULT_TITLE_SENTINEL",
                            "content": [
                                {"type": "text", "text": "SEARCH_RESULT_TEXT_SENTINEL"}
                            ],
                        }
                    ],
                }
            ]
        },
        ("SEARCH_RESULT_TITLE_SENTINEL", "SEARCH_RESULT_TEXT_SENTINEL"),
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
        "top_cache_control",
        {"cache_control": {"type": "ephemeral", "ttl": "5m"}},
        ("MATRIX_BASE_USER",),
    ),
    (
        "container",
        {"container": {"id": "container_matrix"}},
        ("MATRIX_BASE_USER",),
    ),
    (
        "inference_geo_service_tier",
        {"inference_geo": "global", "service_tier": "auto"},
        ("MATRIX_BASE_USER",),
    ),
    (
        "metadata_user_profile",
        {
            "metadata": {"user_id": "matrix-user"},
            "user_profile_id": "matrix-profile",
        },
        ("MATRIX_BASE_USER",),
    ),
    (
        "adaptive_thinking_output_effort",
        {
            "thinking": {"type": "adaptive", "display": "summarized"},
            "output_config": {"effort": "high"},
        },
        ("MATRIX_BASE_USER", "high"),
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
        "custom_tool_all_fields",
        {
            "tools": [
                tool(
                    strict=True,
                    eager_input_streaming=True,
                    defer_loading=False,
                    input_examples=[{"value": "TOOL_EXAMPLE_SENTINEL"}],
                    allowed_callers=["direct"],
                    cache_control={"type": "ephemeral", "ttl": "5m"},
                )
            ],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": False},
        },
        ("matrix_tool", "MATRIX_TOOL_DESCRIPTION", "TOOL_EXAMPLE_SENTINEL"),
    ),
    (
        "multiple_stop_sequences",
        {"stop_sequences": ["STOP_ONE_SENTINEL", "STOP_TWO_SENTINEL"]},
        ("STOP_ONE_SENTINEL", "STOP_TWO_SENTINEL"),
    ),
    (
        "server_tool_use_history",
        {
            "messages": [
                {"role": "user", "content": "SERVER_TOOL_USER"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_search",
                            "name": "web_search",
                            "input": {"query": "SERVER_TOOL_QUERY_SENTINEL"},
                        }
                    ],
                },
                {"role": "user", "content": "SERVER_TOOL_CONTINUE"},
            ]
        },
        ("SERVER_TOOL_QUERY_SENTINEL", "SERVER_TOOL_CONTINUE"),
    ),
    (
        "web_search_result_history",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_web_search",
                            "name": "web_search",
                            "input": {"query": "q"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "web_search_tool_result",
                            "tool_use_id": "srvtoolu_web_search",
                            "content": {
                                "type": "web_search_tool_result_error",
                                "error_code": "query_too_long",
                            },
                        }
                    ],
                },
            ]
        },
        ("query_too_long",),
    ),
    (
        "web_fetch_and_code_execution_results",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_fetch",
                            "name": "web_fetch",
                            "input": {"url": "https://example.invalid"},
                        },
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_code",
                            "name": "code_execution",
                            "input": {"code": "print(1)"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "web_fetch_tool_result",
                            "tool_use_id": "srvtoolu_fetch",
                            "content": {
                                "type": "web_fetch_tool_result_error",
                                "error_code": "url_not_accessible",
                            },
                        },
                        {
                            "type": "code_execution_tool_result",
                            "tool_use_id": "srvtoolu_code",
                            "content": {
                                "type": "code_execution_tool_result_error",
                                "error_code": "execution_time_exceeded",
                            },
                        },
                    ],
                },
            ]
        },
        ("url_not_accessible", "execution_time_exceeded"),
    ),
    (
        "bash_and_text_editor_results",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_bash",
                            "name": "bash_code_execution",
                            "input": {"command": "false"},
                        },
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_editor",
                            "name": "text_editor_code_execution",
                            "input": {"path": "/tmp/missing"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "bash_code_execution_tool_result",
                            "tool_use_id": "srvtoolu_bash",
                            "content": {
                                "type": "bash_code_execution_tool_result_error",
                                "error_code": "output_file_too_large",
                            },
                        },
                        {
                            "type": "text_editor_code_execution_tool_result",
                            "tool_use_id": "srvtoolu_editor",
                            "content": {
                                "type": "text_editor_code_execution_tool_result_error",
                                "error_code": "file_not_found",
                                "error_message": "EDITOR_RESULT_SENTINEL",
                            },
                        },
                    ],
                },
            ]
        },
        ("output_file_too_large", "file_not_found", "EDITOR_RESULT_SENTINEL"),
    ),
    (
        "tool_search_and_container_upload",
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "server_tool_use",
                            "id": "srvtoolu_tool_search",
                            "name": "tool_search_tool_regex",
                            "input": {"pattern": "weather"},
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_search_tool_result",
                            "tool_use_id": "srvtoolu_tool_search",
                            "content": {
                                "type": "tool_search_tool_result_error",
                                "error_code": "unavailable",
                                "error_message": "TOOL_SEARCH_RESULT_SENTINEL",
                            },
                        },
                        {
                            "type": "container_upload",
                            "file_id": "CONTAINER_UPLOAD_FILE_SENTINEL",
                        },
                    ],
                },
            ]
        },
        ("TOOL_SEARCH_RESULT_SENTINEL", "CONTAINER_UPLOAD_FILE_SENTINEL"),
    ),
]


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
                    "schema": {"type": "object", "properties": {}},
                }
            }
        },
    ),
    ("user_profile", {"user_profile_id": "count-profile"}),
]


@pytest.mark.parametrize(
    ("case_name", "extra"), COUNT_CASES, ids=[case[0] for case in COUNT_CASES]
)
def test_count_tokens_request_variants(
    shared_server: RustServer,
    case_name: str,
    extra: dict[str, Any],
) -> None:
    before = len(shared_server.captures())
    tokenizer_before = len(shared_server.tokenizer_captures())
    result = sdk(shared_server.base_url).messages.count_tokens(
        model=MODEL,
        messages=[{"role": "user", "content": f"COUNT_{case_name}"}],
        **extra,
    )
    assert result.input_tokens > 0
    assert len(shared_server.captures()) == before
    observed = [
        capture["token_count"]
        for capture in shared_server.tokenizer_captures()[tokenizer_before:]
    ]
    assert observed
    assert result.input_tokens in observed or result.input_tokens == sum(observed)


INVALID_CASES: list[tuple[str, dict[str, Any]]] = [
    ("missing_max_tokens", {"model": MODEL, "messages": [{"role": "user", "content": "x"}]}),
    ("empty_messages", {"model": MODEL, "max_tokens": 8, "messages": []}),
    (
        "invalid_role",
        {"model": MODEL, "max_tokens": 8, "messages": [{"role": "developer", "content": "x"}]},
    ),
    (
        "unknown_content_block",
        {
            "model": MODEL,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": [{"type": "unknown", "value": "x"}]}],
        },
    ),
]


@pytest.mark.parametrize(
    ("case_name", "body"), INVALID_CASES, ids=[case[0] for case in INVALID_CASES]
)
def test_invalid_request_returns_anthropic_error(
    shared_server: RustServer,
    case_name: str,
    body: dict[str, Any],
) -> None:
    response = httpx2.post(
        f"{shared_server.base_url}/v1/messages",
        headers={
            "content-type": "application/json",
            "x-api-key": "matrix-key",
            "anthropic-version": "2023-06-01",
        },
        json=body,
        timeout=20,
    )
    assert response.status_code == 400, {"case": case_name, "body": response.text}
    payload = response.json()
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "invalid_request_error"


MULTIMODAL_CASES: list[tuple[str, dict[str, Any]]] = [
    (
        "base64_image",
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": "iVBORw0KGgo=",
            },
        },
    ),
    (
        "url_image",
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.invalid/image.png"},
        },
    ),
    (
        "base64_document",
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": "JVBERi0xLjQ=",
            },
        },
    ),
]


@pytest.mark.parametrize(
    ("case_name", "block"), MULTIMODAL_CASES, ids=[case[0] for case in MULTIMODAL_CASES]
)
def test_unsupported_backend_media_fails_cleanly(
    shared_server: RustServer,
    case_name: str,
    block: dict[str, Any],
) -> None:
    with pytest.raises(anthropic.BadRequestError) as caught:
        sdk(shared_server.base_url).messages.create(
            model=MODEL,
            max_tokens=8,
            messages=[{"role": "user", "content": [block]}],
        )
    assert caught.value.status_code == 400, case_name
    assert caught.value.body["error"]["type"] == "invalid_request_error"
