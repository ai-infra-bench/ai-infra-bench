#!/usr/bin/env python3
"""Exercise both Anthropic endpoints through the official Python SDK."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

import anthropic


MODEL = "Qwen3.6-27B"
MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Please check the GPU status for vLLM."},
    {"role": "assistant", "content": "Sure, I will check it."},
    {"role": "user", "content": "Show me the nvidia-smi output."},
    {
        "role": "assistant",
        "content": "The GPU status looks normal, with utilization around 15%.",
    },
    {"role": "user", "content": "Write up the results as a report."},
    {
        "role": "system",
        "content": (
            "Task instruction: Based on the conversation above, generate a brief "
            "GPU status report."
        ),
    },
    {"role": "user", "content": "Please summarize the above."},
]


def invoke(name: str, call: Callable[[], Any]) -> tuple[bool, dict[str, Any]]:
    try:
        response = call()
        if name == "messages":
            assert response.role == "assistant"
            assert response.model == MODEL
            return True, {
                "status": 200,
                "role": response.role,
                "stop_reason": response.stop_reason,
            }
        assert response.input_tokens > 0
        return True, {"status": 200, "input_tokens": response.input_tokens}
    except anthropic.APIStatusError as exc:
        return False, {
            "status": exc.status_code,
            "body": exc.response.text,
        }
    except Exception as exc:  # Preserve useful server/client failure evidence.
        return False, {"exception": type(exc).__name__, "message": str(exc)}


def main() -> int:
    client = anthropic.Anthropic(
        api_key="test",
        base_url=os.environ["ANTHROPIC_BASE_URL"],
        timeout=60,
        max_retries=0,
    )
    results = {}
    ok_count, results["count_tokens"] = invoke(
        "count_tokens",
        lambda: client.messages.count_tokens(model=MODEL, messages=MESSAGES),
    )
    ok_messages, results["messages"] = invoke(
        "messages",
        lambda: client.messages.create(
            model=MODEL,
            max_tokens=1,
            messages=MESSAGES,
        ),
    )
    print(json.dumps(results, ensure_ascii=False, sort_keys=True))
    return 0 if ok_count and ok_messages else 1


if __name__ == "__main__":
    sys.exit(main())
