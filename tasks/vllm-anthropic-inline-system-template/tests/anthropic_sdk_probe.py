#!/usr/bin/env python3
"""Observe both API modes and compare counting with generation's actual usage."""
from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

from probe_contract import MODE_SPECS, cases


def error(exc):
    if isinstance(exc, anthropic.APIStatusError):
        return {"ok": False, "status": exc.status_code, "body": exc.response.text}
    return {"ok": False, "exception": type(exc).__name__, "message": str(exc)}


def prompt_tokens(usage):
    # This server reports prompt_tokens as input_tokens. The optional cache
    # details are not enabled and must not be subtracted from that total.
    value = usage.input_tokens
    assert type(value) is int and value > 0
    return value


def request_args(model, case):
    result = {"model": model, "messages": case["messages"]}
    if "system" in case:
        result["system"] = case["system"]
    return result


def count_tokens(client, kwargs):
    try:
        response = client.messages.count_tokens(**kwargs)
        assert type(response.input_tokens) is int and response.input_tokens > 0
        return {"ok": True, "input_tokens": response.input_tokens}
    except Exception as exc:
        return error(exc)


def create_message(client, kwargs):
    try:
        response = client.messages.create(**kwargs, max_tokens=1)
        assert response.role == "assistant"
        return {"ok": True, "role": response.role,
                "input_tokens": prompt_tokens(response.usage)}
    except Exception as exc:
        return error(exc)


def stream_message(client, kwargs):
    try:
        with client.messages.stream(**kwargs, max_tokens=1) as stream:
            events = [event.type for event in stream]
            final = stream.get_final_message()
        assert events[0] == "message_start" and events[-1] == "message_stop"
        assert final.role == "assistant"
        return {"ok": True, "role": final.role, "events": len(events),
                "first_event": events[0], "last_event": events[-1],
                "input_tokens": prompt_tokens(final.usage)}
    except Exception as exc:
        return error(exc)


def reference_counts(mode, inventory):
    # These conversations already work with their templates and their layout
    # must be preserved. Independently tokenize them with the unmodified HF
    # runtime, not with a vLLM candidate helper or a reference-solution patch.
    # Strict templates may validly join system text with different separators;
    # for those, compare against the real generation prompt usage instead.
    if MODE_SPECS[mode]["family"] not in {"permissive", "context"}:
        return {}
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        "/opt/models/qwen-template", local_files_only=True, trust_remote_code=True,
    )
    template = Path(os.environ["PROBE_TEMPLATE_PATH"]).read_text()
    return {
        name: len(tokenizer.apply_chat_template(
            case["messages"], chat_template=template, tokenize=True,
            add_generation_prompt=True, return_dict=False,
        ))
        for name, case in inventory.items()
    }


def main():
    mode = os.environ["PROBE_MODE"]
    inventory = cases(mode)
    results = {}
    expected = reference_counts(mode, inventory)
    with anthropic.Anthropic(
        api_key="test", base_url=os.environ["ANTHROPIC_BASE_URL"],
        timeout=30, max_retries=0,
    ) as client:
        for name, case in inventory.items():
            kwargs = request_args(os.environ["SERVED_MODEL"], case)
            result = {
                "count_tokens": count_tokens(client, kwargs),
                "messages": create_message(client, kwargs),
            }
            if case.get("stream"):
                result["stream"] = stream_message(client, kwargs)
            results[name] = result
    payload = {"mode": mode, "completed": True, "cases": results,
               "reference_counts": expected}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)
    return 0 if all(op["ok"] for case in results.values() for op in case.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
