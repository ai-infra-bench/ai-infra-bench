from __future__ import annotations

import json
import socket
import subprocess
import sys
import time

import httpx

from verifier_support import data_chunks, parse_sse, request_body, stream_request


def main() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "/tests/stream_server.py", "--port", str(port)]
    )
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/docs", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.05)
        else:
            raise RuntimeError("HTTP server did not become ready")

        endpoint = f"http://127.0.0.1:{port}/inference/v1/generate"
        stream_response, stream_lines = stream_request(
            endpoint,
            request_body(
                977,
                stream_options={
                    "include_usage": True,
                    "continuous_usage_stats": True,
                },
            ),
        )
        nonstream = httpx.post(endpoint, json=request_body(978, stream=False), timeout=15)
        stream_is_sse = stream_response.headers["content-type"].startswith(
            "text/event-stream"
        )
        stream_has_sse_lines = bool(stream_lines) and all(
            line.startswith("data: ") for line in stream_lines
        )
        parsed = parse_sse(stream_lines) if stream_has_sse_lines else []
        chunks = data_chunks(parsed)
        stream_has_done = bool(parsed) and parsed[-1] == "[DONE]"
        streamed_tokens = [
            item["choices"][0]["token_ids"]
            for item in chunks
            if item.get("choices")
        ]
        stream_tokens_valid = streamed_tokens == [[71], [72, 73], [74]]
        final_usage_valid = bool(chunks) and chunks[-1].get("choices") == []

        nonstream_is_json = nonstream.headers["content-type"].startswith(
            "application/json"
        )
        nonstream_body = nonstream.json()
        nonstream_tokens_valid = (
            nonstream_body["choices"][0]["token_ids"] == [71, 72, 73, 74]
        )

        print(
            json.dumps(
                {
                    "entrypoint": "real FastAPI route over uvicorn TCP with SSE and JSON response lifecycles",
                    "stream_status": stream_response.status_code,
                    "stream_content_type": stream_response.headers["content-type"],
                    "stream_lines": stream_lines,
                    "stream_has_done": stream_has_done,
                    "stream_tokens_valid": stream_tokens_valid,
                    "final_usage_valid": final_usage_valid,
                    "nonstream_status": nonstream.status_code,
                    "nonstream_content_type": nonstream.headers["content-type"],
                    "nonstream_tokens_valid": nonstream_tokens_valid,
                },
                separators=(",", ":"),
            )
        )
        assert stream_response.status_code == 200
        assert stream_is_sse
        assert stream_has_done
        assert stream_tokens_valid
        assert final_usage_valid
        assert nonstream.status_code == 200
        assert nonstream_is_json
        assert nonstream_tokens_valid
        return 0
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
