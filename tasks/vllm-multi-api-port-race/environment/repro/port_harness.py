from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import Any


def _tiny_model(path: str) -> str:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.json"
    if not config.exists():
        config.write_text(
            json.dumps(
                {
                    "architectures": ["OPTForCausalLM"],
                    "model_type": "opt",
                    "hidden_size": 64,
                    "ffn_dim": 128,
                    "num_attention_heads": 4,
                    "num_hidden_layers": 1,
                    "vocab_size": 128,
                    "max_position_embeddings": 512,
                    "word_embed_proj_dim": 64,
                }
            )
        )
    return str(root)


def make_config(model_dir: str, *, tcp: bool):
    from vllm.config import (
        CacheConfig,
        ModelConfig,
        ParallelConfig,
        SchedulerConfig,
        VllmConfig,
    )

    model = ModelConfig(
        model=_tiny_model(model_dir),
        dtype="float16",
        skip_tokenizer_init=True,
    )
    parallel = ParallelConfig(
        data_parallel_size=2 if tcp else 1,
        data_parallel_size_local=1,
        data_parallel_rank=0,
        data_parallel_master_ip="127.0.0.1",
    )
    return VllmConfig(
        model_config=model,
        parallel_config=parallel,
        scheduler_config=SchedulerConfig(
            max_num_seqs=8,
            max_num_batched_tokens=128,
            max_model_len=512,
            is_encoder_decoder=model.is_encoder_decoder,
        ),
        cache_config=CacheConfig(
            block_size=16,
            gpu_memory_utilization=0.9,
            cache_dtype="auto",
        ),
    )


def mpclient_worker(_listen, _sock, args, client_config) -> None:
    from vllm.v1.engine.core_client import MPClient

    if args.worker_delay:
        time.sleep(args.worker_delay)
    config = make_config(args.model_dir, tcp=args.tcp)
    MPClient(
        asyncio_mode=False,
        vllm_config=config,
        executor_class=object,
        log_stats=False,
        client_addresses=client_config,
    )


def crashing_worker(_listen, _sock, _args, _client_config) -> None:
    raise RuntimeError("synthetic API worker startup failure")


def _port(uri: str) -> int:
    if not uri.startswith("tcp://"):
        return -1
    return int(uri.rsplit(":", 1)[1])


def run_scenario(
    mode: str,
    *,
    servers: int,
    worker_delay: float = 0.0,
) -> dict[str, Any]:
    import vllm
    import vllm.v1.engine.utils as engine_utils
    import vllm.v1.utils as process_utils
    from vllm.entrypoints.cli import serve

    model_dir = tempfile.mkdtemp(prefix="port-race-model-")
    tcp = mode != "ipc"
    config = make_config(model_dir, tcp=tcp)
    state: dict[str, Any] = {}
    squatters: list[socket.socket] = []
    original_async_engine_args = vllm.AsyncEngineArgs
    original_executor_get_class = serve.Executor.__dict__["get_class"]
    original_setup_prometheus = serve.setup_multiprocess_prometheus
    original_setup_server = serve.setup_server
    original_launch = serve.launch_core_engines
    original_wait = serve.wait_for_completion_or_failure
    original_worker = process_utils.run_api_server_worker_proc
    original_rust_path = serve.envs.VLLM_RUST_FRONTEND_PATH
    original_rust_manager = serve.RustFrontendProcessManager

    class FakeAsyncEngineArgs:
        disable_log_stats = True

        @classmethod
        def from_cli_args(cls, _args):
            return cls()

        def create_engine_config(self, **_kwargs):
            return config

    @contextlib.contextmanager
    def fake_launch(_config, _executor, _log_stats, addresses, _count=1):
        yield None, None, addresses, None
        state["inputs"] = list(addresses.inputs)
        state["outputs"] = list(addresses.outputs)

    def fake_wait(*, api_server_manager, **_kwargs):
        if not api_server_manager.processes:
            return
        # A corrected startup has already received every child's bound
        # endpoints before reaching this hook. The legacy path has no such
        # handshake, so give a pressured or crashing child time to reach its
        # real ZMQ bind instead of treating a freshly spawned PID as ready.
        must_observe_exit = mode == "crash" or (mode == "race" and squatters)
        deadline = time.monotonic() + 12.0

        def endpoint_ready(uri: str) -> bool:
            if uri.startswith("ipc://"):
                return Path(uri.removeprefix("ipc://")).exists()
            port = _port(uri)
            if port <= 0:
                return False
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.05)
            try:
                return probe.connect_ex(("127.0.0.1", port)) == 0
            finally:
                probe.close()

        while time.monotonic() < deadline:
            failed = [
                proc
                for proc in api_server_manager.processes
                if proc.exitcode is not None and proc.exitcode != 0
            ]
            if failed:
                proc = failed[0]
                raise RuntimeError(
                    f"Process {proc.name} died with exit code {proc.exitcode}"
                )
            endpoints = [*state.get("inputs", []), *state.get("outputs", [])]
            if (
                not must_observe_exit
                and endpoints
                and all(endpoint_ready(uri) for uri in endpoints)
            ):
                api_server_manager.shutdown(timeout=1.0)
                return
            time.sleep(0.01)
        if must_observe_exit:
            raise RuntimeError("pressured API server unexpectedly remained alive")
        raise RuntimeError("API server sockets did not become reachable")

    original_addresses = engine_utils.get_engine_zmq_addresses

    def pressured_addresses(*args, **kwargs):
        addresses = original_addresses(*args, **kwargs)
        if mode != "race":
            return addresses
        for uri in dict.fromkeys([*addresses.inputs, *addresses.outputs]):
            port = _port(uri)
            if port <= 0:
                continue
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(("127.0.0.1", port))
                sock.listen(1)
            except OSError:
                sock.close()
            else:
                squatters.append(sock)
        return addresses

    class FakeRustManager:
        processes: list[Any] = []

        def __init__(self, **kwargs):
            state["inputs"] = [kwargs["input_address"]]
            state["outputs"] = [kwargs["output_address"]]

        def shutdown(self, timeout=None):
            return None

    args = argparse.Namespace(
        headless=False,
        api_server_count=servers,
        model_dir=model_dir,
        worker_delay=worker_delay,
        tcp=tcp,
    )
    serve.setup_multiprocess_prometheus = lambda: None
    serve.setup_server = lambda _args: ("127.0.0.1:0", None)
    vllm.AsyncEngineArgs = FakeAsyncEngineArgs
    serve.Executor.get_class = staticmethod(lambda _config: object)
    serve.launch_core_engines = fake_launch
    serve.wait_for_completion_or_failure = fake_wait
    engine_utils.get_engine_zmq_addresses = pressured_addresses
    process_utils.run_api_server_worker_proc = (
        crashing_worker if mode == "crash" else mpclient_worker
    )
    if mode == "rust":
        serve.envs.VLLM_RUST_FRONTEND_PATH = "/tmp/fake-vllm-rs"
        serve.RustFrontendProcessManager = FakeRustManager
    else:
        serve.envs.VLLM_RUST_FRONTEND_PATH = None

    started = time.monotonic()
    try:
        serve.run_multi_api_server(args)
    except BaseException as exc:
        result: dict[str, Any] = {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    else:
        result = {"status": "ok"}
    finally:
        for sock in squatters:
            sock.close()
        vllm.AsyncEngineArgs = original_async_engine_args
        serve.Executor.get_class = original_executor_get_class
        serve.setup_multiprocess_prometheus = original_setup_prometheus
        serve.setup_server = original_setup_server
        serve.launch_core_engines = original_launch
        serve.wait_for_completion_or_failure = original_wait
        engine_utils.get_engine_zmq_addresses = original_addresses
        process_utils.run_api_server_worker_proc = original_worker
        serve.envs.VLLM_RUST_FRONTEND_PATH = original_rust_path
        serve.RustFrontendProcessManager = original_rust_manager
    result["elapsed_seconds"] = time.monotonic() - started
    result["mode"] = mode
    result["servers"] = servers
    result["inputs"] = state.get("inputs", [])
    result["outputs"] = state.get("outputs", [])
    result["ports"] = [
        _port(uri) for uri in [*result["inputs"], *result["outputs"]]
    ]
    return result
