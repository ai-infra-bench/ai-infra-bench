from __future__ import annotations

import json

import pytest

from verifier_support import CHAT_PATH, COMPLETION_PATH, MODEL, RenderServer, decode, encode


def chunk(server, path, ids, state=None, *, request_id="stream-request", index=0,
          finish=None, usage=None, choices=True):
    payload = {
        "stream": True,
        "model": MODEL,
        "generate_chunk": {
            "request_id": request_id,
            "choices": ([{"index": index, "token_ids": ids, "finish_reason": finish}] if choices else []),
        },
        "stream_state": state,
    }
    if usage is not None:
        payload["generate_chunk"]["usage"] = usage
    result = server.post(path, payload)
    assert isinstance(result["stream_state"], dict)
    assert result["chunk"]["id"] == request_id
    assert result["chunk"]["model"] == MODEL
    return result["chunk"], json.loads(json.dumps(result["stream_state"]))


def text_of(result, path):
    return "".join(
        (choice["delta"].get("content") or "") if path == CHAT_PATH else choice["text"]
        for choice in result["choices"]
    )


@pytest.mark.parametrize("path", [CHAT_PATH, COMPLETION_PATH], ids=["chat", "completion"])
@pytest.mark.parametrize("sizes", [[1], [1, 4, 2, 7], [13, 2, 3]], ids=["single-token", "mixed", "large-first"])
def test_partition_invariance_across_instances(plain, tmp_path, path, sizes):
    ids = encode('北京🍣 café e\u0301 and quotes "\\"; 最后。\nSecond line.')
    state = None
    fragments = []
    roles = []
    with RenderServer(tmp_path / "second") as other:
        offset = 0
        step = 0
        while offset < len(ids):
            size = sizes[step % len(sizes)]
            part = ids[offset:offset + size]
            response, state = chunk(plain if step % 2 == 0 else other, path, part, state, index=3)
            assert response["choices"][0]["index"] == 3
            fragments.append(text_of(response, path))
            if path == CHAT_PATH:
                roles.append(response["choices"][0]["delta"].get("role"))
            offset += len(part)
            step += 1
        terminal, state = chunk(other, path, [], state, index=3, finish="length",
                                usage={"prompt_tokens": 19, "completion_tokens": len(ids), "total_tokens": 19 + len(ids)})
        fragments.append(text_of(terminal, path))
        assert terminal["choices"][0]["finish_reason"] == "length"
        assert terminal["usage"]["total_tokens"] == 19 + len(ids)
    assert "".join(fragments) == decode(ids)
    if path == CHAT_PATH:
        assert roles.count("assistant") == 1


@pytest.mark.parametrize("path", [CHAT_PATH, COMPLETION_PATH], ids=["chat", "completion"])
def test_client_state_survives_original_server_exit(tmp_path, path):
    ids = encode("跨进程恢复🍣 requires no live original process.")
    # Stop in the middle of a character: restarting from only the remaining
    # IDs cannot accidentally pass as it could at an ordinary text boundary.
    cut = next(i for i in range(1, len(ids)) if decode(ids[:i]).endswith("\ufffd"))
    with RenderServer(tmp_path / "original") as original:
        first, state = chunk(original, path, ids[:cut])
    with RenderServer(tmp_path / "replacement") as replacement:
        rest, state = chunk(replacement, path, ids[cut:], state, finish="stop")
    assert text_of(first, path) + text_of(rest, path) == decode(ids)


def test_interleaved_streams_have_independent_state(plain):
    texts = ["stream A 北京🍣", "stream B café ☕", "stream C 日本語"]
    inputs = [encode(text) for text in texts]
    states = [None, None, None]
    results = ["", "", ""]
    for offset in range(max(map(len, inputs))):
        for i, ids in enumerate(inputs):
            if offset < len(ids):
                response, states[i] = chunk(plain, CHAT_PATH, ids[offset:offset + 1], states[i], request_id=f"interleave-{i}")
                results[i] += text_of(response, CHAT_PATH)
    assert results == texts


def test_usage_only_chunk_does_not_consume_initial_role(plain):
    first, state = chunk(plain, CHAT_PATH, [], choices=False,
                         usage={"prompt_tokens": 9, "completion_tokens": 0, "total_tokens": 9})
    assert first["choices"] == []
    second, state = chunk(plain, CHAT_PATH, encode("hello"), state)
    assert second["choices"][0]["delta"]["role"] == "assistant"
    final, _ = chunk(plain, CHAT_PATH, [], state, choices=False,
                     usage={"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10})
    assert final["usage"]["completion_tokens"] == 1
    assert final["choices"] == []


@pytest.mark.parametrize("path", [CHAT_PATH, COMPLETION_PATH], ids=["chat", "completion"])
def test_chunked_request_requires_structured_state(plain, path):
    payload = {"stream": True, "generate_chunk": {"request_id": "invalid-state", "choices": []}, "stream_state": ["invalid"]}
    response = plain.client.post(path, json=payload)
    assert 400 <= response.status_code < 500
    assert plain.client.get("/health").status_code == 200


@pytest.mark.parametrize("skip_special", [False, True], ids=["retain-markers", "skip-markers"])
def test_independent_special_token_resume_challenge(plain, tmp_path, skip_special):
    # Added after the initial Oracle and Python runs. Unlike the original
    # plain-text stream cases this crosses a special token and a split emoji,
    # while carrying the original completion decoding options between hosts.
    ids = encode("left<|im_end|>right🍣")
    state = None
    fragments = []
    with RenderServer(tmp_path / "challenge-receiver") as other:
        for index, token_id in enumerate(ids):
            result = (plain if index % 2 == 0 else other).post(COMPLETION_PATH, {
                "stream": True,
                "model": MODEL,
                "completion_request": {"model": MODEL, "prompt": "context", "skip_special_tokens": skip_special},
                "generate_chunk": {"request_id": "independent-challenge", "choices": [{"index": 0, "token_ids": [token_id]}]},
                "stream_state": state,
            })
            fragments.append(result["chunk"]["choices"][0]["text"])
            state = json.loads(json.dumps(result["stream_state"]))
    assert "".join(fragments) == decode(ids, skip_special=skip_special)
