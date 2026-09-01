from __future__ import annotations

import json
import os
import signal
import subprocess


def run_scenario(
    mode: str,
    *,
    servers: int,
    delay: float = 0.0,
    ready_timeout: int | None = None,
) -> dict:
    command = [
        "python",
        "/tests/run_scenario.py",
        mode,
        "--servers",
        str(servers),
        "--delay",
        str(delay),
    ]
    if ready_timeout is not None:
        command.extend(["--ready-timeout", str(ready_timeout)])
    process = subprocess.Popen(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        stdout, _ = process.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, _ = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, _ = process.communicate(timeout=5)
        raise AssertionError(f"scenario {mode} timed out:\n{stdout}")
    lines = [line for line in stdout.splitlines() if line.startswith("{")]
    assert lines, stdout
    result = json.loads(lines[-1])
    result["process_returncode"] = process.returncode
    result["raw_output"] = stdout
    return result


def assert_bound_tcp_endpoints(result: dict, servers: int) -> None:
    assert result["status"] == "ok", result
    assert result["process_returncode"] == 0
    assert len(result["inputs"]) == servers
    assert len(result["outputs"]) == servers
    assert len(result["ports"]) == 2 * servers
    assert all(port > 0 for port in result["ports"])
    assert len(set(result["ports"])) == len(result["ports"])
