from __future__ import annotations

import json

import pytest

from verifier_support import CHAT_PATH, MODEL, decode, encode, generation, request_context, tool_definition


def tool_output(city, count=2):
    payload = {"name": "lookup_city", "arguments": {"city": city, "count": count}}
    return "<tool_call>\n" + json.dumps(payload, ensure_ascii=False) + "\n</tool_call>"


@pytest.mark.parametrize("city", ["Paris", "北京🍣", 'Oslo "quoted" \\ city'], ids=["ascii", "unicode", "escaped"])
def test_tool_arguments_are_reconstructed(tools_server, city):
    raw = tool_output(city, 7)
    context = request_context(tools=[tool_definition()], tool_choice="auto")
    result = tools_server.post(CHAT_PATH, {"model": MODEL, "generate_response": generation(raw), "chat_request": context})
    message = result["choices"][0]["message"]
    assert len(message["tool_calls"]) == 1
    call = message["tool_calls"][0]
    assert call["id"]
    assert call["type"] == "function"
    assert call["function"]["name"] == "lookup_city"
    assert json.loads(call["function"]["arguments"]) == {"city": city, "count": 7}
    assert "<tool_call>" not in (message.get("content") or "")


def test_multiple_tools_keep_order_and_unique_ids(tools_server):
    output = tool_output("Tokyo", 1) + "\n" + tool_output("Berlin", 3)
    result = tools_server.post(CHAT_PATH, {"generate_response": generation(output), "chat_request": request_context(tools=[tool_definition()], tool_choice="auto")})
    calls = result["choices"][0]["message"]["tool_calls"]
    assert len(calls) == 2
    assert len({call["id"] for call in calls}) == 2
    assert [json.loads(call["function"]["arguments"]) for call in calls] == [{"city": "Tokyo", "count": 1}, {"city": "Berlin", "count": 3}]


def test_text_then_tool_preserves_both(tools_server):
    result = tools_server.post(CHAT_PATH, {"generate_response": generation("Let me check.\n" + tool_output("Lima")), "chat_request": request_context(tools=[tool_definition()], tool_choice="auto")})
    message = result["choices"][0]["message"]
    assert "Let me check." in message["content"]
    assert message["tool_calls"][0]["function"]["name"] == "lookup_city"


@pytest.mark.parametrize("include", [True, False], ids=["include", "hide"])
def test_reasoning_uses_real_prompt_context(reasoning_server, include):
    context = request_context(include_reasoning=include)
    rendered = reasoning_server.post("/v1/chat/completions/render", context)
    # This model template opens reasoning in the prompt; output does not repeat
    # the opener. This checks request context, not a candidate helper.
    assert "<think>" in decode(rendered["token_ids"], skip_special=False)
    raw = "Check both alternatives.\n</think>\nThe answer is ready."
    result = reasoning_server.post(CHAT_PATH, {"generate_response": generation(raw), "chat_request": context})
    message = result["choices"][0]["message"]
    assert "The answer is ready." in message["content"]
    assert "Check both alternatives." not in message["content"]
    if include:
        assert "Check both alternatives." in message["reasoning"]
    else:
        assert not message.get("reasoning")


def test_reasoning_then_tool_parses_both(reasoning_server):
    context = request_context(tools=[tool_definition()], tool_choice="auto", include_reasoning=True)
    raw = "A lookup is needed.</think>\n" + tool_output("Oslo")
    result = reasoning_server.post(CHAT_PATH, {"generate_response": generation(raw), "chat_request": context})
    message = result["choices"][0]["message"]
    assert "A lookup is needed." in message["reasoning"]
    assert json.loads(message["tool_calls"][0]["function"]["arguments"])["city"] == "Oslo"


def logprobs_for(ids):
    return {"content": [{"token": f"token_id:{tid}", "logprob": -0.125 * (i + 1), "bytes": None,
                         "top_logprobs": [{"token": f"token_id:{tid}", "logprob": -0.125 * (i + 1), "bytes": None}]}
                        for i, tid in enumerate(ids)]}


@pytest.mark.parametrize("text", ["hello world", "北京🍣 café"], ids=["ascii", "unicode"])
def test_logprobs_resolve_token_ids_and_bytes(plain, text):
    ids = encode(text)
    gen = generation(text)
    gen["choices"][0]["logprobs"] = logprobs_for(ids)
    result = plain.post(CHAT_PATH, {"generate_response": gen})
    entries = result["choices"][0]["logprobs"]["content"]
    assert len(entries) == len(ids)
    assert "".join(entry["token"] for entry in entries) == text
    for i, entry in enumerate(entries):
        assert entry["logprob"] == pytest.approx(-0.125 * (i + 1))
        assert entry["bytes"] == list(entry["token"].encode("utf-8"))
        assert entry["top_logprobs"][0]["token"] == entry["token"]
        assert entry["top_logprobs"][0]["logprob"] == entry["logprob"]


def test_completion_logprobs_have_parallel_arrays(plain):
    from verifier_support import COMPLETION_PATH
    text = "hello world"
    ids = encode(text)
    gen = generation(text)
    gen["choices"][0]["logprobs"] = logprobs_for(ids)
    result = plain.post(COMPLETION_PATH, {"generate_responses": [gen]})
    lp = result["choices"][0]["logprobs"]
    assert len(lp["tokens"]) == len(lp["token_logprobs"]) == len(lp["top_logprobs"]) == len(lp["text_offset"]) == len(ids)
    assert "".join(lp["tokens"]) == text
    offset = 0
    for i, token in enumerate(lp["tokens"]):
        assert lp["text_offset"][i] == offset
        assert lp["token_logprobs"][i] == pytest.approx(-0.125 * (i + 1))
        offset += len(token)
