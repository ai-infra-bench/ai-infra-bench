#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any

import anthropic


def cases(mode: str) -> dict[str, dict[str, Any]]:
    if mode == "permissive":
        return {
            "inline_position_preserved": {
                "messages": [
                    {"role": "user", "content": "PERMISSIVE_USER_1"},
                    {"role": "assistant", "content": "PERMISSIVE_ASSISTANT"},
                    {"role": "system", "content": "PERMISSIVE_INLINE_SENTINEL"},
                    {"role": "user", "content": "PERMISSIVE_USER_2"},
                ],
                "stream": True,
            }
        }
    if mode == "restrictive_sentinel":
        return {
            "all_system_content_preserved": {
                "messages": [
                    {"role": "system", "content": "LEAD_SENTINEL"},
                    {"role": "user", "content": "diagnostic user turn"},
                    {"role": "assistant", "content": "diagnostic assistant turn"},
                    {"role": "system", "content": "INLINE_SENTINEL"},
                    {"role": "user", "content": "continue"},
                ],
                "stream": True,
            }
        }
    return {
        "production_issue_shape": {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Check the GPU status for vLLM."},
                {"role": "assistant", "content": "I will check it."},
                {"role": "user", "content": "Show the nvidia-smi output."},
                {"role": "assistant", "content": "Utilization is around 15%."},
                {"role": "user", "content": "Write a report."},
                {"role": "system", "content": "Summarize the conversation as a GPU report."},
                {"role": "user", "content": "Please summarize it."},
            ],
            "stream": True,
        },
        "inline_after_user_without_leading_system": {
            "messages": [
                {"role": "user", "content": "Earlier context"},
                {"role": "assistant", "content": "Earlier response"},
                {"role": "system", "content": "Apply the hidden task instruction."},
                {"role": "user", "content": "Continue."},
            ]
        },
        "multiple_inline_system_messages": {
            "messages": [
                {"role": "system", "content": "Global instruction."},
                {"role": "user", "content": "First question"},
                {"role": "system", "content": "First auxiliary instruction."},
                {"role": "assistant", "content": "Intermediate answer"},
                {"role": "system", "content": "Second auxiliary instruction."},
                {"role": "user", "content": "Final question"},
            ],
            "stream": True,
        },
        "top_level_and_inline_system": {
            "system": "TOP_LEVEL_SYSTEM_SENTINEL",
            "messages": [
                {"role": "user", "content": "User context"},
                {"role": "system", "content": "INLINE_SYSTEM_SENTINEL"},
                {"role": "user", "content": "Final request"},
            ]
        },
        "system_text_blocks": {
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "Leading block."}]},
                {"role": "user", "content": "Context"},
                {"role": "system", "content": [
                    {"type": "text", "text": "Inline block one."},
                    {"type": "text", "text": "Inline block two."},
                ]},
                {"role": "user", "content": "Continue"},
            ]
        },
        "empty_inline_system": {
            "messages": [
                {"role": "system", "content": "Leading instruction."},
                {"role": "user", "content": "Context"},
                {"role": "system", "content": ""},
                {"role": "user", "content": "Continue"},
            ]
        },
        "long_context_inline_system": {
            "messages": [
                {"role": "system", "content": "Global policy."},
                *[
                    {"role": "user" if index % 2 == 0 else "assistant",
                     "content": f"Historical turn {index}: " + "context " * 20}
                    for index in range(12)
                ],
                {"role": "system", "content": "Compress the history before answering."},
                {"role": "user", "content": "Give the final answer."},
            ]
        },
    }


def error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, anthropic.APIStatusError):
        return {"ok": False, "status": exc.status_code, "body": exc.response.text}
    return {"ok": False, "exception": type(exc).__name__, "message": str(exc)}


def count_tokens(client, model, case):
    try:
        kwargs = {"model": model, "messages": case["messages"]}
        if "system" in case:
            kwargs["system"] = case["system"]
        response = client.messages.count_tokens(**kwargs)
        assert response.input_tokens > 0
        return {"ok": True, "status": 200, "input_tokens": response.input_tokens}
    except Exception as exc:
        return error(exc)


def create_message(client, model, case):
    try:
        kwargs = {"model": model, "max_tokens": 1, "messages": case["messages"]}
        if "system" in case:
            kwargs["system"] = case["system"]
        response = client.messages.create(**kwargs)
        assert response.role == "assistant"
        return {"ok": True, "status": 200, "role": response.role,
                "stop_reason": response.stop_reason}
    except Exception as exc:
        return error(exc)


def stream_message(client, model, case):
    try:
        kwargs = {"model": model, "max_tokens": 1, "messages": case["messages"]}
        if "system" in case:
            kwargs["system"] = case["system"]
        event_count = 0
        with client.messages.stream(**kwargs) as stream:
            for _ in stream:
                event_count += 1
            final = stream.get_final_message()
        assert final.role == "assistant"
        assert event_count > 0
        return {"ok": True, "status": 200, "events": event_count,
                "role": final.role}
    except Exception as exc:
        return error(exc)


def main() -> int:
    mode = os.environ["PROBE_MODE"]
    model = os.environ["SERVED_MODEL"]
    client = anthropic.Anthropic(api_key="test", base_url=os.environ["ANTHROPIC_BASE_URL"],
                                 timeout=60, max_retries=0)
    results = {}
    for name, case in cases(mode).items():
        result = {
            "count_tokens": count_tokens(client, model, case),
            "messages": create_message(client, model, case),
        }
        if case.get("stream"):
            result["stream"] = stream_message(client, model, case)
        results[name] = result
    payload = {"mode": mode, "model": model, "cases": results}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if all(
        operation["ok"]
        for case in results.values()
        for operation in case.values()
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
