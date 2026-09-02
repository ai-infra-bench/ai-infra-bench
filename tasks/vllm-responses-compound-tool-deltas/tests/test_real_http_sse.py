from __future__ import annotations

import json
import socket
import threading
import time
from importlib.metadata import version
from importlib.resources import files

import httpx
import uvicorn
import yaml
from fastapi import FastAPI
from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_toolcall_response import (
    parse_toolcall_actions_response,
)
from pyarrow import parquet

from vllm.entrypoints.openai.responses.api_router import attach_router

from kimi_output_mock import (
    BASH_TOOL_CHUNKS,
    EXPECTED_BASH_ARGUMENTS,
    HIDDEN_BASH_ARGUMENTS,
    HIDDEN_BASH_TOOL_CHUNKS,
    PARALLEL_BASH_ARGUMENTS,
    PARALLEL_TOOL_CHUNKS,
)
from verifier_support import build_kimi_serving


def request_body(prompt: str) -> dict:
    tools = [
        {
            "type": "function",
            "name": "bash",
            "description": "Execute a bash command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    },
                },
                "required": ["command"],
            },
        }
    ]
    return {
        "model": "moonshotai/Kimi-K2.5",
        "input": prompt,
        "stream": True,
        "store": False,
        "tool_choice": "auto",
        "tools": tools,
    }


def read_events(url: str, body: dict) -> tuple[list[dict], str | None]:
    events = []
    try:
        with httpx.stream("POST", url, json=body, timeout=30) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
    except httpx.RemoteProtocolError as error:
        return events, str(error)
    return events, None


def completed_calls(events: list[dict]) -> list[dict]:
    return [
        event["item"]
        for event in events
        if event["type"] == "response.output_item.done"
        and event["item"]["type"] == "function_call"
    ]


def parsed_arguments(call: dict) -> dict | None:
    try:
        value = json.loads(call["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def parse_error(call: dict) -> str | None:
    try:
        json.loads(call["arguments"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        return str(error)
    return None


def mini_swe_actions(calls: list[dict]) -> tuple[list[dict], str | None]:
    config_path = files("minisweagent").joinpath("config/benchmarks/swebench.yaml")
    config = yaml.safe_load(config_path.read_text())
    try:
        actions = parse_toolcall_actions_response(
            calls,
            format_error_template=config["model"]["format_error_template"],
        )
    except FormatError as error:
        message = error.messages[0]
        return [], message["content"][0]["text"]
    return actions, None


def verify_swe_bench_instance() -> str:
    path = "/opt/swe-bench-verified/test.parquet"
    assert parquet.ParquetFile(path).metadata.num_rows == 500
    table = parquet.read_table(
        path,
        filters=[("instance_id", "=", "astropy__astropy-12907")],
    )
    rows = table.to_pylist()
    row = next(item for item in rows if item["instance_id"] == "astropy__astropy-12907")
    assert row["repo"] == "astropy/astropy"
    assert "astropy/modeling/separable.py" in row["patch"]
    assert "astropy/modeling/tests/test_separable.py" in row["test_patch"]
    hidden = parquet.read_table(
        path,
        filters=[("instance_id", "=", "astropy__astropy-13033")],
    ).to_pylist()[0]
    assert hidden["repo"] == "astropy/astropy"
    assert "astropy/timeseries/core.py" in hidden["patch"]
    assert "astropy/timeseries/tests/test_sampled.py" in hidden["test_patch"]
    return row["instance_id"]


def main() -> int:
    app = FastAPI()
    attach_router(app)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", lifespan="off")
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

    root = f"http://127.0.0.1:{port}/v1/responses"
    try:
        mini_swe_version = version("mini-swe-agent")
        assert mini_swe_version == "2.3.0"
        dataset_instance = verify_swe_bench_instance()
        app.state.openai_serving_responses = build_kimi_serving(BASH_TOOL_CHUNKS)
        one, one_stream_error = read_events(
            root,
            request_body(
                "Inspect the relevant implementation and run its focused tests."
            ),
        )
        one_calls = completed_calls(one)
        one_arguments = parsed_arguments(one_calls[0]) if len(one_calls) == 1 else None
        one_raw_arguments = one_calls[0]["arguments"] if len(one_calls) == 1 else ""
        one_parse_error = parse_error(one_calls[0]) if len(one_calls) == 1 else None
        one_actions, one_mini_swe_error = mini_swe_actions(one_calls)

        app.state.openai_serving_responses = build_kimi_serving(
            HIDDEN_BASH_TOOL_CHUNKS
        )
        hidden, hidden_stream_error = read_events(
            root,
            request_body("Inspect another failing task and run its focused tests."),
        )
        hidden_calls = completed_calls(hidden)
        hidden_actions, hidden_mini_swe_error = mini_swe_actions(hidden_calls)
        hidden_valid = (
            hidden_stream_error is None
            and len(hidden_calls) == 1
            and hidden_calls[0]["name"] == "bash"
            and parsed_arguments(hidden_calls[0]) == HIDDEN_BASH_ARGUMENTS
            and [action["command"] for action in hidden_actions]
            == [HIDDEN_BASH_ARGUMENTS["command"]]
        )

        app.state.openai_serving_responses = build_kimi_serving(
            PARALLEL_TOOL_CHUNKS
        )
        parallel, parallel_stream_error = read_events(
            root,
            request_body("Use parallel tools."),
        )
        parallel_calls = completed_calls(parallel)
        parallel_arguments = [parsed_arguments(call) for call in parallel_calls]
        parallel_actions, parallel_mini_swe_error = mini_swe_actions(parallel_calls)
        parallel_summaries = [
            {
                "name": call.get("name"),
                "argument_prefix": call.get("arguments", "")[:120],
                "parse_error": parse_error(call),
            }
            for call in parallel_calls
        ]
        single_valid = (
            one_stream_error is None
            and one_arguments == EXPECTED_BASH_ARGUMENTS
            and [action["command"] for action in one_actions]
            == [EXPECTED_BASH_ARGUMENTS["command"]]
        )
        parallel_valid = (
            parallel_stream_error is None
            and
            [call["name"] for call in parallel_calls]
            == ["bash", "bash"]
            and parallel_arguments
            == PARALLEL_BASH_ARGUMENTS
            and [action["command"] for action in parallel_actions]
            == [item["command"] for item in PARALLEL_BASH_ARGUMENTS]
        )
        print(
            json.dumps(
                {
                    "entrypoint": "real vLLM POST /v1/responses router over TCP",
                    "mini_swe_agent_version": mini_swe_version,
                    "swe_bench_instance": dataset_instance,
                    "single_tool_events": len(one),
                    "single_stream_error": one_stream_error,
                    "parallel_tool_events": len(parallel),
                    "completed_calls": (
                        len(one_calls) + len(hidden_calls) + len(parallel_calls)
                    ),
                    "single_tool_valid": single_valid,
                    "single_argument_prefix": one_raw_arguments[:160],
                    "single_parse_error": one_parse_error,
                    "single_mini_swe_error": one_mini_swe_error,
                    "single_call": one_calls[0] if len(one_calls) == 1 else None,
                    "hidden_tool_valid": hidden_valid,
                    "hidden_stream_error": hidden_stream_error,
                    "hidden_mini_swe_error": hidden_mini_swe_error,
                    "parallel_tools_valid": parallel_valid,
                    "parallel_stream_error": parallel_stream_error,
                    "parallel_mini_swe_error": parallel_mini_swe_error,
                    "parallel_call_summaries": parallel_summaries,
                    "parallel_calls": parallel_calls,
                },
                separators=(",", ":"),
            )
        )
        assert single_valid
        assert hidden_valid
        assert parallel_valid
        return 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive()


if __name__ == "__main__":
    raise SystemExit(main())
