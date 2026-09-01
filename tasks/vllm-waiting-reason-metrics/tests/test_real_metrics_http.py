from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import Response

from verifier_support import metric_value, prometheus_output


root = Path(tempfile.mkdtemp(prefix="waiting-metrics-http-"))
app = FastAPI()


def optional_metric(text: str, name: str, *, engine: int, reason: str | None = None):
    try:
        return metric_value(text, name, engine=engine, reason=reason)
    except AssertionError:
        return None


@app.get("/metrics")
def metrics() -> Response:
    return Response(
        prometheus_output(root, [(2, 3), (0, 1)]),
        media_type="text/plain; version=0.0.4",
    )


def main() -> int:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", lifespan="off")
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/metrics", timeout=30)
        text = response.text
        observed = {
            "engine_0": {
                "total": optional_metric(
                    text, "vllm:num_requests_waiting", engine=0
                ),
                "capacity": optional_metric(
                    text,
                    "vllm:num_requests_waiting_by_reason",
                    engine=0,
                    reason="capacity",
                ),
                "deferred": optional_metric(
                    text,
                    "vllm:num_requests_waiting_by_reason",
                    engine=0,
                    reason="deferred",
                ),
            },
            "engine_1": {
                "total": optional_metric(
                    text, "vllm:num_requests_waiting", engine=1
                ),
                "capacity": optional_metric(
                    text,
                    "vllm:num_requests_waiting_by_reason",
                    engine=1,
                    reason="capacity",
                ),
                "deferred": optional_metric(
                    text,
                    "vllm:num_requests_waiting_by_reason",
                    engine=1,
                    reason="deferred",
                ),
            },
        }
        print(
            json.dumps(
                {
                    "entrypoint": "GET /metrics over TCP",
                    "status": response.status_code,
                    **observed,
                },
                separators=(",", ":"),
            )
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert observed["engine_0"] == {
            "total": 5,
            "capacity": 2,
            "deferred": 3,
        }
        assert observed["engine_1"] == {
            "total": 1,
            "capacity": 0,
            "deferred": 1,
        }
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
