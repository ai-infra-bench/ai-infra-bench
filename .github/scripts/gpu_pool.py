#!/usr/bin/env python3
"""Cooperative GPU leases shared by this host's trusted CI runners."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

POOL_LABEL = "io.ai-infra-bench.pool"
GPU_LABEL = "io.ai-infra-bench.gpu."


class Cancelled(Exception):
    pass


class Pool:
    def __init__(self, config_path: Path):
        config = json.loads(config_path.read_text())
        self.devices = config["gpu_uuids"]
        if (
            not isinstance(self.devices, list)
            or not self.devices
            or any(not isinstance(d, str) or not re.fullmatch(r"GPU-[0-9a-f-]{36}", d) for d in self.devices)
            or len(set(self.devices)) != len(self.devices)
        ):
            raise ValueError("gpu_uuids must be a nonempty list of unique GPU UUIDs")
        self.state = Path(config["state_dir"])
        if not self.state.is_absolute():
            raise ValueError("state_dir must be absolute and shared by all runners")
        self.state.mkdir(parents=True, exist_ok=True)
        self.identity = hashlib.sha256(",".join(self.devices).encode()).hexdigest()[:16]

    @staticmethod
    def _try_lock(path):
        handle = path.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return None
        return handle

    @contextmanager
    def acquire(self, count, timeout=7200):
        if count not in (1, 2, 4) or count > len(self.devices):
            raise ValueError(f"unsupported GPU request: {count}; pool size: {len(self.devices)}")
        deadline = time.monotonic() + timeout
        admission = None
        selected = []
        try:
            # The waiter holding admission prevents later small requests from
            # taking free devices while its larger request is draining the pool.
            while admission is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting to enter GPU pool")
                admission = self._try_lock(self.state / "admission.lock")
                if admission is None:
                    time.sleep(0.1)
            while True:
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for enough GPUs")
                for index in range(len(self.devices)):
                    handle = self._try_lock(self.state / f"gpu-{index}.lock")
                    if handle is not None:
                        selected.append((index, handle))
                    if len(selected) == count:
                        break
                if len(selected) == count:
                    break
                for _, handle in selected:
                    handle.close()
                selected.clear()
                time.sleep(0.1)
            admission.close()
            admission = None
            yield selected
        finally:
            if admission is not None:
                admission.close()
            for _, handle in selected:
                handle.close()

    def cleanup(self, selected):
        """Only remove containers carrying our pool and leased-slot labels."""
        containers = set()
        for index, _ in selected:
            result = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"label={POOL_LABEL}={self.identity}",
                 "--filter", f"label={GPU_LABEL}{index}=true"],
                check=True, capture_output=True, text=True, timeout=30,
            )
            containers.update(result.stdout.split())
        if containers:
            subprocess.run(["docker", "rm", "-f", *sorted(containers)], check=True, timeout=120)

    def run(self, count, command, timeout=7200):
        with self.acquire(count, timeout) as selected:
            # A previous runner might have died after starting a container.
            # No process still holding these GPU leases can be alive here.
            self.cleanup(selected)
            devices = [self.devices[index] for index, _ in selected]
            labels = {POOL_LABEL: self.identity}
            labels.update({f"{GPU_LABEL}{index}": "true" for index, _ in selected})
            env = os.environ.copy()
            env.update(
                AI_INFRA_GPU_UUIDS=",".join(devices),
                AI_INFRA_GPU_LABELS=json.dumps(labels),
                CUDA_VISIBLE_DEVICES=",".join(devices),
            )
            print(json.dumps({"event": "gpu_acquired", "gpu_uuids": devices}), flush=True)
            child = None
            try:
                # Harbor itself inherits the locks. If this supervisor is killed,
                # the lease stays held until Harbor can no longer create containers.
                child = subprocess.Popen(
                    command, env=env, start_new_session=True,
                    pass_fds=tuple(handle.fileno() for _, handle in selected),
                )
                return child.wait()
            finally:
                # Finish cleanup even if GitHub sends repeated cancellation signals.
                old_handlers = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
                try:
                    if child is not None:
                        try:
                            os.killpg(child.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                        try:
                            child.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            os.killpg(child.pid, signal.SIGKILL)
                            child.wait()
                        # The parent can exit before a child such as Compose.
                        # Stop remaining descendants before removing containers.
                        try:
                            os.killpg(child.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    self.cleanup(selected)
                    print(json.dumps({"event": "gpu_released", "gpu_uuids": devices}), flush=True)
                finally:
                    for signum, handler in old_handlers.items():
                        signal.signal(signum, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=os.environ.get("AI_INFRA_GPU_POOL_CONFIG"))
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--timeout", type=float, default=7200)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.config is None or not command:
        parser.error("a host-managed --config and command are required")
    def cancel(signum, frame):
        raise Cancelled(signum)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, cancel)
    try:
        return Pool(args.config).run(args.count, command, args.timeout)
    except Cancelled as error:
        return 128 + error.args[0]
    except (ValueError, TimeoutError, OSError, subprocess.SubprocessError) as error:
        print(f"GPU pool error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
