from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from verifier_support import (
    CHAT_PATH, COMPLETION_PATH, MODEL, decode, encode, generation, request_context,
)


TEXTS = [
    "A short independent result.",
    "北京🍣，第二个答案。",
    "العربية café e\u0301 日本語",
    'Quotes " and backslash \\ with\nnewlines\tand spaces.',
    "many tokens with changing content 0123456789 " * 24,
]


@pytest.mark.parametrize("text", TEXTS, ids=["ascii", "cjk-emoji", "multilingual", "escaped", "long"])
def test_chat_text_and_exact_usage(plain, text):
    gen = generation(text, request_id="caller-id")
    result = plain.post(CHAT_PATH, {"model": MODEL, "generate_response": gen, "prompt_tokens": 37})
    assert result["id"] == "caller-id"
    assert result["object"] == "chat.completion"
    assert result["model"] == MODEL
    choice = result["choices"][0]
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == decode(encode(text))
    assert choice["finish_reason"] == "stop"
    assert result["usage"]["prompt_tokens"] == 37
    assert result["usage"]["completion_tokens"] == len(encode(text))
    assert result["usage"]["total_tokens"] == 37 + len(encode(text))


@pytest.mark.parametrize("text", TEXTS[:4], ids=["ascii", "cjk-emoji", "multilingual", "escaped"])
def test_completion_text(plain, text):
    result = plain.post(COMPLETION_PATH, {"model": MODEL, "generate_responses": [generation(text)], "prompt_tokens": [11]})
    assert result["object"] == "text_completion"
    assert result["choices"][0]["text"] == decode(encode(text))
    assert result["usage"]["total_tokens"] == 11 + len(encode(text))


def test_chat_multiple_choices_preserve_identity(plain):
    texts = ["first candidate", "另一种答案", "last candidate"]
    choices = [generation(text, index=i)["choices"][0] for i, text in zip([4, 8, 2], texts)]
    result = plain.post(CHAT_PATH, {"generate_response": {"request_id": "multi", "choices": choices}, "prompt_tokens": 17})
    assert result["model"] == MODEL
    assert [c["index"] for c in result["choices"]] == [4, 8, 2]
    assert [c["message"]["content"] for c in result["choices"]] == texts
    assert result["usage"]["completion_tokens"] == sum(len(encode(t)) for t in texts)
    assert result["usage"]["prompt_tokens"] == 17


def test_completion_multi_prompt_and_choice_accounting(plain):
    first = generation("one", index=9, request_id="first")
    first["choices"].append(generation("two", index=12)["choices"][0])
    second = generation("three", index=7, request_id="second")
    result = plain.post(COMPLETION_PATH, {"generate_responses": [first, second], "prompt_tokens": [13, 29]})
    assert [c["index"] for c in result["choices"]] == [0, 1, 2]
    assert [c["text"] for c in result["choices"]] == ["one", "two", "three"]
    assert result["usage"]["prompt_tokens"] == 42
    assert result["usage"]["completion_tokens"] == sum(len(encode(t)) for t in ["one", "two", "three"])


@pytest.mark.parametrize("reason", ["length", "stop"], ids=["length", "stop"])
def test_finish_reason_is_preserved(plain, reason):
    for path, key in [(CHAT_PATH, "generate_response"), (COMPLETION_PATH, "generate_responses")]:
        gen = generation("finished output", finish_reason=reason)
        result = plain.post(path, {key: gen if path == CHAT_PATH else [gen]})
        assert result["choices"][0]["finish_reason"] == reason


def test_transfer_and_prompt_metadata_survive(plain):
    tid = encode("hello")[0]
    prompt_lp = [None, {str(tid): {"logprob": -0.125, "rank": 1, "decoded_token": "hello"}}]
    params = {"remote_engine_id": "engine-metadata", "remote_block_ids": [8, 3]}
    gen = generation("kept", prompt_logprobs=prompt_lp, kv_transfer_params=params)
    result = plain.post(CHAT_PATH, {"generate_response": gen})
    assert result["prompt_logprobs"] == prompt_lp
    assert result["kv_transfer_params"] == params
    assert result["usage"]["prompt_tokens"] == 0


@pytest.mark.parametrize("skip_special", [False, True], ids=["retain", "skip"])
def test_special_token_setting(plain, skip_special):
    ids = encode("prefix<|im_end|>suffix")
    gen = generation("placeholder")
    gen["choices"][0]["token_ids"] = ids
    result = plain.post(CHAT_PATH, {"generate_response": gen, "chat_request": request_context(skip_special_tokens=skip_special)})
    assert result["choices"][0]["message"]["content"] == decode(ids, skip_special=skip_special)


def test_concurrent_nonstream_requests_are_isolated(plain):
    def request(i):
        text = f"concurrent-{i}-北京🍣"
        result = plain.post(CHAT_PATH, {"generate_response": generation(text, request_id=f"request-{i}")})
        return result["id"], result["choices"][0]["message"]["content"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(request, range(12)))
    assert results == [(f"request-{i}", f"concurrent-{i}-北京🍣") for i in range(12)]


@pytest.mark.parametrize("path,payload", [
    (CHAT_PATH, {}),
    (CHAT_PATH, {"generate_response": {"choices": [{"index": 0, "token_ids": []}]}}),
    (CHAT_PATH, {"generate_response": {"choices": [{"index": 0, "token_ids": [-1]}]}}),
    (COMPLETION_PATH, {"generate_responses": []}),
    (COMPLETION_PATH, {"generate_responses": [generation("valid")], "prompt_tokens": [1, 2]}),
], ids=["missing-generation", "empty-tokens", "negative-token", "empty-batch", "prompt-count-mismatch"])
def test_invalid_input_fails_cleanly(plain, path, payload):
    response = plain.client.post(path, json=payload)
    assert 400 <= response.status_code < 500, response.text
    assert plain.client.get("/health").status_code == 200


def test_unknown_model_is_not_served(plain):
    response = plain.client.post(CHAT_PATH, json={"model": "missing-model", "generate_response": generation("text")})
    assert response.status_code == 404


def test_existing_health_models_and_render(plain):
    assert plain.client.get("/health").status_code == 200
    models = plain.client.get("/v1/models").json()
    assert MODEL in [item["id"] for item in models["data"]]
    rendered = plain.post("/v1/chat/completions/render", request_context())
    assert rendered["token_ids"]
    assert "Explain the result." in decode(rendered["token_ids"], skip_special=False)
    completion = plain.post("/v1/completions/render", {"model": MODEL, "prompt": "Preserve rendering", "max_tokens": 8})
    assert len(completion) == 1
    assert "Preserve rendering" in decode(completion[0]["token_ids"], skip_special=False)
