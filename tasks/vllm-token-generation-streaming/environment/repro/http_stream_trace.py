from __future__ import annotations

import json
import socket
import subprocess
import sys
import time

import httpx


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_ready(port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{port}/docs", timeout=0.2).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.05)
    raise RuntimeError("local token server did not start")


def main() -> int:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, "/opt/repro/stream_server.py", "--port", str(port)]
    )
    try:
        wait_ready(port)
        url = f"http://127.0.0.1:{port}/inference/v1/generate"
        body = {
            "request_id": "public-stream-trace",
            "token_ids": [128000, 9906, 11, 1268, 527, 499, 30],
            "sampling_params": {"max_tokens": 8},
            "stream": True,
        }
        with httpx.stream("POST", url, json=body, timeout=10) as response:
            lines = [line for line in response.iter_lines() if line]
            content_type = response.headers.get("content-type")
        nonstream = httpx.post(url, json={**body, "stream": False}, timeout=10)
        result = {
            "stream_status": response.status_code,
            "stream_content_type": content_type,
            "stream_lines": lines,
            "nonstream_status": nonstream.status_code,
            "nonstream_content_type": nonstream.headers.get("content-type"),
            "nonstream_body": nonstream.json(),
        }
        print(json.dumps(result, indent=2))
        passed = (
            response.status_code == 200
            and content_type is not None
            and content_type.startswith("text/event-stream")
            and lines[-1] == "data: [DONE]"
            and len(lines) >= 4
            and nonstream.status_code == 200
            and nonstream.headers["content-type"].startswith("application/json")
        )
        print(f"token_stream_http_contract={passed}")
        return 0 if passed else 3
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
