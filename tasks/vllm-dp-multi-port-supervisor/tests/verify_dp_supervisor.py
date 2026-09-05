#!/usr/bin/env python3
"""Black-box contract for the public node-local DP serving mode.

Only heavyweight model serving is replaced. The verifier launches the normal
``vllm serve`` command and observes its CLI, HTTP and process-tree behaviour;
it does not require a particular supervisor module, class or helper name.
"""

from __future__ import annotations

import errno
import os
import signal
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import psutil

sys.path.insert(0, "/workspace/repo")


FAKE_SERVER = r'''\
import asyncio
import os
import signal

from aiohttp import web
import vllm.platforms
from vllm.platforms.cpu import CpuPlatform

# The task exercises frontend orchestration without reserving a GPU. Make the
# otherwise GPU-only image's platform discovery deterministic before the CLI
# constructs its configuration defaults.
vllm.platforms._current_platform = CpuPlatform()

import vllm.entrypoints.openai.api_server as api_server


async def fake_run_server(args, **_kwargs):
    healthy = False
    stopped = asyncio.Event()

    async def health(_request):
        return web.Response(status=200 if healthy else 503)

    async def set_healthy(_request):
        nonlocal healthy
        healthy = True
        return web.Response(status=200)

    async def set_unhealthy(_request):
        nonlocal healthy
        healthy = False
        return web.Response(status=200)

    async def device(_request):
        return web.Response(text=os.environ.get(CpuPlatform.device_control_env_var, ""))

    async def rank(_request):
        return web.Response(text=str(args.data_parallel_rank))

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/set_healthy", set_healthy)
    app.router.add_get("/set_unhealthy", set_unhealthy)
    app.router.add_get("/device", device)
    app.router.add_get("/rank", rank)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host or "127.0.0.1", args.port)
    await site.start()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stopped.set)
    try:
        await stopped.wait()
    finally:
        await runner.cleanup()


api_server.run_server = fake_run_server
'''


def reserve_ports(count: int = 3) -> tuple[int, ...]:
    for first in range(23100, 32000 - count):
        sockets: list[socket.socket] = []
        try:
            for port in range(first, first + count):
                sock = socket.socket()
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("127.0.0.1", port))
                sockets.append(sock)
            return tuple(range(first, first + count))
        except OSError:
            pass
        finally:
            for sock in sockets:
                sock.close()
    raise RuntimeError("could not reserve contiguous loopback ports")


def status(port: int, path: str = "/health") -> int:
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=0.5) as response:
            return response.status
    except HTTPError as exc:
        return exc.code
    except (TimeoutError, URLError):
        return -1


def response_text(port: int, path: str) -> str:
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=0.5) as response:
        assert response.status == 200
        return response.read().decode()


def wait_status(
    port: int,
    expected: int,
    path: str = "/health",
    timeout: float = 45.0,
) -> None:
    deadline = time.monotonic() + timeout
    observed = -1
    while time.monotonic() < deadline:
        observed = status(port, path)
        if observed == expected:
            return
        time.sleep(0.05)
    raise AssertionError(f"{port}{path}: expected {expected}, observed {observed}")


def wait_closed(*ports: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # An HTTP timeout does not prove that a listener released its socket.
        # Only an explicit local TCP refusal establishes absence of a listener;
        # connection success, timeout and other errors must keep this check open.
        refused = []
        for port in ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                refused.append(
                    probe.connect_ex(("127.0.0.1", port)) == errno.ECONNREFUSED
                )
        if all(refused):
            return
        time.sleep(0.05)
    raise AssertionError(f"ports remained reachable: {ports}")


def command(
    first: int,
    supervisor_port: int,
    *,
    data_parallel_size: int = 2,
    data_parallel_size_local: int = 2,
    data_parallel_start_rank: int = 0,
    tensor_parallel_size: int = 1,
    pipeline_parallel_size: int = 1,
    probe_failure_threshold: int = 1,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        "benchmark/fake-model",
        "--host",
        "127.0.0.1",
        "--port",
        str(first),
        "--data-parallel-supervisor-port",
        str(supervisor_port),
        "--data-parallel-size",
        str(data_parallel_size),
        "--data-parallel-size-local",
        str(data_parallel_size_local),
        "--data-parallel-start-rank",
        str(data_parallel_start_rank),
        "--tensor-parallel-size",
        str(tensor_parallel_size),
        "--pipeline-parallel-size",
        str(pipeline_parallel_size),
        "--data-parallel-multi-port-external-lb",
        "--dp-supervisor-probe-interval-s",
        "0.1",
        "--dp-supervisor-probe-timeout-s",
        "0.2",
        "--dp-supervisor-probe-failure-threshold",
        str(probe_failure_threshold),
        "--uvicorn-log-level",
        "warning",
    ]


def launch(
    harness: Path,
    first: int,
    supervisor_port: int,
    *,
    visible_devices: str = "0,1",
    data_parallel_size: int = 2,
    data_parallel_size_local: int = 2,
    data_parallel_start_rank: int = 0,
    tensor_parallel_size: int = 1,
    pipeline_parallel_size: int = 1,
    probe_failure_threshold: int = 1,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(harness), "/workspace/repo", env.get("PYTHONPATH", "")]
    )
    env["CUDA_VISIBLE_DEVICES"] = visible_devices
    return subprocess.Popen(
        command(
            first,
            supervisor_port,
            data_parallel_size=data_parallel_size,
            data_parallel_size_local=data_parallel_size_local,
            data_parallel_start_rank=data_parallel_start_rank,
            tensor_parallel_size=tensor_parallel_size,
            pipeline_parallel_size=pipeline_parallel_size,
            probe_failure_threshold=probe_failure_threshold,
        ),
        cwd="/workspace/repo",
        env=env,
        # Keep startup diagnostics visible in verifier logs. They are especially
        # useful when the public CLI rejects a candidate before binding ports.
        stdout=None,
        stderr=None,
        start_new_session=True,
    )


def wait_exited(children: list[psutil.Process], timeout: float = 15.0) -> None:
    """Check retained process identities even after their parent exits."""
    _, alive = psutil.wait_procs(children, timeout=timeout)
    assert not alive, f"orphaned processes: {[child.pid for child in alive]}"


def terminate(
    process: subprocess.Popen[bytes],
    children: list[psutil.Process] | tuple[psutil.Process, ...] = (),
) -> None:
    # Cleanup must also work after an incorrect supervisor has already exited.
    # Retain Process objects (PID + creation time), rather than rediscovering
    # children from a dead parent or signalling potentially reused PIDs.
    for child in children:
        try:
            for descendant in child.children(recursive=True):
                descendant.kill()
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
    psutil.wait_procs(children, timeout=5)


def rank_processes(pid: int, ports: tuple[int, ...]) -> list[psutil.Process]:
    """Resolve rank processes from their public listening ports.

    Multiprocessing may also create a resource-tracker child, and alternative
    implementations may use a different process title or nesting structure.
    Neither is part of the serving contract.
    """
    descendants = {child.pid for child in psutil.Process(pid).children(recursive=True)}
    owners: dict[int, psutil.Process] = {}
    for connection in psutil.net_connections(kind="tcp"):
        if (
            connection.pid in descendants
            and connection.status == psutil.CONN_LISTEN
            and connection.laddr
            and connection.laddr.port in ports
        ):
            owners[connection.laddr.port] = psutil.Process(connection.pid)
    assert set(owners) == set(ports), f"rank listener ownership mismatch: {owners}"
    return [owners[port] for port in ports]


def verify_invalid_cli(harness: Path) -> None:
    first, _, _ = reserve_ports()
    process = launch(harness, first, first + 1)
    try:
        assert process.wait(timeout=15) != 0, "overlapping child/supervisor ports were accepted"
        assert status(first) == -1, "invalid CLI left a child endpoint behind"
    finally:
        terminate(process)


def verify_readiness_and_child_failure(harness: Path) -> None:
    first, second, supervisor_port = reserve_ports()
    process = launch(harness, first, supervisor_port)
    tracked: list[psutil.Process] = []
    try:
        wait_status(supervisor_port, 503)
        wait_status(first, 503)
        wait_status(second, 503)
        assert response_text(first, "/device") == "0"
        assert response_text(second, "/device") == "1"
        assert status(first, "/set_healthy") == 200
        time.sleep(0.25)
        assert status(supervisor_port) == 503
        assert status(second, "/set_healthy") == 200
        for path in ("/health", "/ready", "/readyz"):
            wait_status(supervisor_port, 200, path)

        victim, sibling = rank_processes(process.pid, (first, second))
        tracked = psutil.Process(process.pid).children(recursive=True)
        victim.kill()
        process.wait(timeout=15)
        sibling.wait(timeout=10)
        assert not sibling.is_running(), "surviving rank was orphaned"
        wait_exited(tracked)
        wait_closed(first, second, supervisor_port)
    finally:
        terminate(process, tracked)


def verify_unhealthy_shutdown(harness: Path) -> None:
    first, second, supervisor_port = reserve_ports()
    process = launch(harness, first, supervisor_port)
    tracked: list[psutil.Process] = []
    try:
        wait_status(first, 503)
        wait_status(second, 503)
        assert status(first, "/set_healthy") == 200
        assert status(second, "/set_healthy") == 200
        wait_status(supervisor_port, 200)
        tracked = psutil.Process(process.pid).children(recursive=True)
        assert status(first, "/set_unhealthy") == 200
        process.wait(timeout=15)
        wait_exited(tracked)
        wait_closed(first, second, supervisor_port)
    finally:
        terminate(process, tracked)


def verify_parallel_rank_and_device_mapping(harness: Path) -> None:
    first, second, supervisor_port = reserve_ports()
    process = launch(
        harness,
        first,
        supervisor_port,
        visible_devices="0,1,2,3,4,5,6,7",
        data_parallel_size=4,
        data_parallel_size_local=2,
        data_parallel_start_rank=2,
        tensor_parallel_size=2,
        pipeline_parallel_size=2,
        probe_failure_threshold=200,
    )
    tracked: list[psutil.Process] = []
    try:
        wait_status(first, 503)
        wait_status(second, 503)
        assert response_text(first, "/rank") == "2"
        assert response_text(second, "/rank") == "3"
        assert response_text(first, "/device") == "0,1,2,3"
        assert response_text(second, "/device") == "4,5,6,7"
        assert status(first, "/set_healthy") == 200
        assert status(second, "/set_healthy") == 200
        wait_status(supervisor_port, 200)
        tracked = psutil.Process(process.pid).children(recursive=True)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=15)
        wait_exited(tracked)
        wait_closed(first, second, supervisor_port)
    finally:
        terminate(process, tracked)


def verify_signal_forwarding(harness: Path) -> None:
    first, second, supervisor_port = reserve_ports()
    process = launch(harness, first, supervisor_port)
    tracked: list[psutil.Process] = []
    try:
        wait_status(first, 503)
        wait_status(second, 503)
        children = rank_processes(process.pid, (first, second))
        tracked = psutil.Process(process.pid).children(recursive=True)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=15)
        for child in children:
            child.wait(timeout=10)
            assert not child.is_running(), "termination was not forwarded to a rank"
        wait_exited(tracked)
        wait_closed(first, second, supervisor_port)
    finally:
        terminate(process, tracked)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dp-supervisor-verifier-") as tmp:
        harness = Path(tmp)
        (harness / "sitecustomize.py").write_text(
            textwrap.dedent(FAKE_SERVER), encoding="utf-8"
        )
        verify_invalid_cli(harness)
        verify_readiness_and_child_failure(harness)
        verify_unhealthy_shutdown(harness)
        verify_parallel_rank_and_device_mapping(harness)
        verify_signal_forwarding(harness)
    print(
        "PASS: public CLI supervised readiness, failure cleanup, "
        "rank/device mapping, signals, and sockets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
