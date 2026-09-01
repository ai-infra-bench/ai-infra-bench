from __future__ import annotations

import socket
import subprocess
import sys
import time

import httpx
import pytest

from verifier_support import data_chunks, parse_sse, request_body, stream_request


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def endpoint():
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, "/tests/stream_server.py", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/docs", timeout=0.2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        process.terminate()
        output = process.communicate(timeout=5)[0]
        raise AssertionError(output)
    try:
        yield f"http://127.0.0.1:{port}/inference/v1/generate"
    finally:
        process.terminate()
        process.wait(timeout=10)


def test_basic_stream_uses_sse_deltas_and_done(endpoint: str) -> None:
    response, lines = stream_request(endpoint, request_body())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    parsed = parse_sse(lines)
    assert parsed[-1] == "[DONE]"
    chunks = data_chunks(parsed)
    assert [chunk["choices"][0]["token_ids"] for chunk in chunks] == [
        [71],
        [72, 73],
        [74],
    ]
    assert chunks[-1]["choices"][0]["finish_reason"] == "length"
    assert len({chunk["request_id"] for chunk in chunks}) == 1


def test_first_stream_chunk_arrives_before_generation_finishes(endpoint: str) -> None:
    started = time.monotonic()
    with httpx.stream("POST", endpoint, json=request_body(811), timeout=15) as response:
        iterator = (line for line in response.iter_lines() if line)
        first = next(iterator)
        first_elapsed = time.monotonic() - started
        rest = list(iterator)
        finished_elapsed = time.monotonic() - started
    assert first.startswith("data: {")
    assert first_elapsed + 0.04 < finished_elapsed
    assert rest[-1] == "data: [DONE]"


def test_include_usage_emits_final_usage_only_chunk(endpoint: str) -> None:
    _, lines = stream_request(
        endpoint,
        request_body(812, stream_options={"include_usage": True}),
    )
    chunks = data_chunks(parse_sse(lines))
    final = chunks[-1]
    assert final["choices"] == []
    assert final["usage"] == {
        "prompt_tokens": 4,
        "completion_tokens": 4,
        "total_tokens": 8,
    }


def test_continuous_usage_is_cumulative(endpoint: str) -> None:
    _, lines = stream_request(
        endpoint,
        request_body(
            813,
            stream_options={
                "include_usage": True,
                "continuous_usage_stats": True,
            },
        ),
    )
    chunks = data_chunks(parse_sse(lines))
    assert [chunk["usage"]["completion_tokens"] for chunk in chunks[:-1]] == [1, 3, 4]
    assert chunks[-1]["choices"] == []


def test_error_with_empty_delta_is_not_swallowed(endpoint: str) -> None:
    _, lines = stream_request(endpoint, request_body(901))
    parsed = parse_sse(lines)
    assert parsed[-1] == "[DONE]"
    chunks = data_chunks(parsed)
    assert chunks[0]["choices"][0]["token_ids"] == [71]
    assert "error" in chunks[-1]


def test_empty_non_error_delta_is_skipped(endpoint: str) -> None:
    _, lines = stream_request(endpoint, request_body(902))
    chunks = data_chunks(parse_sse(lines))
    assert [chunk["choices"][0]["token_ids"] for chunk in chunks] == [
        [71],
        [72, 73],
        [74],
    ]


def test_logprobs_follow_each_streamed_token(endpoint: str) -> None:
    _, lines = stream_request(
        endpoint,
        request_body(905, sampling={"max_tokens": 8, "logprobs": 1}),
    )
    for chunk in data_chunks(parse_sse(lines)):
        choice = chunk["choices"][0]
        assert len(choice["logprobs"]["content"]) == len(choice["token_ids"])
        assert all(item["logprob"] == -0.1 for item in choice["logprobs"]["content"])


def test_multiple_choices_keep_indexes_and_usage(endpoint: str) -> None:
    _, lines = stream_request(
        endpoint,
        request_body(
            903,
            sampling={"max_tokens": 8, "n": 2},
            stream_options={"include_usage": True},
        ),
    )
    chunks = data_chunks(parse_sse(lines))
    choices = [chunk["choices"][0] for chunk in chunks if chunk["choices"]]
    assert [choice["index"] for choice in choices] == [0, 1, 0, 1, 0, 1]
    assert chunks[-1]["choices"] == []
    assert chunks[-1]["usage"]["completion_tokens"] == 8


def test_prompt_token_details_are_kept(endpoint: str) -> None:
    _, lines = stream_request(
        endpoint,
        request_body(904, stream_options={"include_usage": True}),
    )
    final = data_chunks(parse_sse(lines))[-1]
    assert final["usage"]["prompt_tokens_details"] == {"cached_tokens": 2}


def test_nonstreaming_response_stays_json(endpoint: str) -> None:
    response = httpx.post(endpoint, json=request_body(906, stream=False), timeout=15)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["choices"][0]["token_ids"] == [71, 72, 73, 74]
    assert body["choices"][0]["finish_reason"] == "length"
