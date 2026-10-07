#!/usr/bin/env python3
"""Parent-owned scoring with authenticated per-case completion checkpoints."""

from __future__ import annotations

import hmac
import _hashlib
import importlib.util
import json
import os
import pwd
import runpy
import secrets
import select
import signal
import socket
import stat
import sys
import time
from pathlib import Path


REWARD = Path("/logs/verifier/reward.txt")
LOG = Path("/logs/verifier/verifier.log")
HERE = Path(__file__).resolve().parent


def trusted(path: Path) -> bool:
    info = path.stat()
    return (
        info.st_uid == 0
        and stat.S_ISREG(info.st_mode)
        and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )


def write_reward(value: int, details: dict) -> None:
    REWARD.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        REWARD, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644
    )
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o644)
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    numeric = {
        "reward": value,
        "completed": int(details.get("completed", 0)),
        "required": int(details.get("required", 0)),
        "failure_count": len(details.get("failures", [])),
        "worker_exit_status": int(details.get("worker_exit_status") or 0),
    }
    (REWARD.parent / "reward.json").write_text(
        json.dumps(numeric, sort_keys=True) + "\n"
    )
    (REWARD.parent / "verifier-details.json").write_text(
        json.dumps(details, sort_keys=True) + "\n"
    )


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 4:
        write_reward(0, {"reward": 0, "error": "bad supervisor invocation"})
        return 0

    python = Path(sys.argv[1]).resolve()
    worker = Path(sys.argv[2]).resolve()
    timeout_sec = int(sys.argv[3])
    extension = HERE / "_checkpoint.so"
    for path in (python, worker, Path(__file__).resolve(), extension):
        if not trusted(path):
            write_reward(0, {"reward": 0, "error": f"untrusted harness file: {path}"})
            return 0

    module = runpy.run_path(str(worker))
    suite = module["run_suite"]
    expected = tuple(module["EXPECTED_CHECKPOINTS"])

    spec = importlib.util.spec_from_file_location("_checkpoint", extension)
    checkpoint = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(checkpoint)

    REWARD.parent.mkdir(parents=True, exist_ok=True)
    os.chown(REWARD.parent, 0, 0)
    REWARD.parent.chmod(0o755)
    write_reward(0, {"reward": 0, "completed": 0, "required": len(expected)})

    account = pwd.getpwnam("agent")
    key = secrets.token_bytes(32)
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    log = open(LOG, "wb", buffering=0)
    pid = os.fork()
    if pid == 0:
        try:
            parent.close()
            checkpoint.configure(
                key, child.fileno(), suite.__code__, json.dumps, _hashlib.hmac_digest
            )
            del key
            os.setsid()
            os.dup2(log.fileno(), 1)
            os.dup2(log.fileno(), 2)
            with open(os.devnull, "rb") as empty:
                os.dup2(empty.fileno(), 0)
            log.close()
            os.initgroups(account.pw_name, account.pw_gid)
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
            os.environ.update(
                HOME=account.pw_dir,
                XDG_CACHE_HOME=account.pw_dir + "/.cache",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                VLLM_NO_USAGE_STATS="1",
            )
            suite(checkpoint.emit)
            child.close()
            os._exit(0)
        except BaseException:
            import traceback

            traceback.print_exc()
            os._exit(1)

    child.close()
    log.close()
    completed = 0
    previous = b""
    failures: list[str] = []
    exit_status: int | None = None
    deadline = time.monotonic() + timeout_sec
    try:
        while completed < len(expected):
            if time.monotonic() >= deadline:
                failures.append("suite timed out before all checkpoints")
                break
            readable, _, _ = select.select([parent], [], [], 0.2)
            if readable:
                packet = parent.recv(65536)
                signature, body = packet[:32], packet[32:]
                wanted = hmac.digest(
                    key, (previous if completed else b"") + body, "sha256"
                )
                if not hmac.compare_digest(signature, wanted):
                    failures.append("unauthenticated checkpoint")
                    break
                observed = json.loads(body)
                name = expected[completed]
                if (
                    observed.get("index") != completed
                    or observed.get("name") != name
                ):
                    failures.append("missing, duplicate, or reordered checkpoint")
                    break
                if observed.get("value") is not True:
                    failures.append(f"failed checkpoint: {name}")
                    break
                previous = signature
                completed += 1
            else:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    exit_status = status
                    failures.append(
                        f"worker exited before completion ({completed}/{len(expected)})"
                    )
                    break

        if exit_status is None:
            until = min(deadline, time.monotonic() + 10)
            while time.monotonic() < until:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    exit_status = status
                    break
                time.sleep(0.1)
        if exit_status != 0:
            failures.append(f"worker did not finish successfully: {exit_status}")
    finally:
        parent.close()
        if exit_status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)

    passed = not failures and completed == len(expected)
    details = {
        "reward": int(passed),
        "completed": completed,
        "required": len(expected),
        "failures": failures,
        "worker_exit_status": exit_status,
    }
    write_reward(int(passed), details)
    if LOG.exists():
        print(LOG.read_text(errors="replace"), end="")
    print(json.dumps(details, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
