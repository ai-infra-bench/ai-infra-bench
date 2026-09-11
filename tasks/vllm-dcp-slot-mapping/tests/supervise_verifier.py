#!/usr/bin/env python3
"""Trusted verifier supervisor for Harbor reward integrity."""

from __future__ import annotations

import fcntl
import json
import os
import pwd
import stat
import subprocess
import sys
from pathlib import Path


REWARD = Path("/logs/verifier/reward.txt")
REWARD_JSON = Path("/logs/verifier/reward.json")
LOG = Path("/logs/verifier/verifier.log")
ENV_PASSTHROUGH = (
    "PATH",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "CUDA_HOME",
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_VISIBLE_DEVICES",
    "NVIDIA_DRIVER_CAPABILITIES",
    "TORCH_HOME",
    "TRITON_CACHE_DIR",
    "HF_HOME",
    "HF_HUB_OFFLINE",
    "TRANSFORMERS_OFFLINE",
    "TMPDIR",
    "LANG",
    "LC_ALL",
)


def write_reward(value: int, payload: dict) -> None:
    REWARD.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        REWARD, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o644)
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    REWARD_JSON.write_text(json.dumps(payload, sort_keys=True) + "\n")


def trusted_regular_file(path: Path) -> str | None:
    try:
        info = path.stat()
    except OSError as exc:
        return f"{path} is not readable: {exc}"
    if info.st_uid != 0:
        return f"{path} is owned by uid {info.st_uid}, not root"
    if not stat.S_ISREG(info.st_mode):
        return f"{path} is not a regular file"
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return f"{path} is group/other writable"
    return None


def main() -> int:
    if os.geteuid() != 0 or len(sys.argv) != 6:
        write_reward(0, {"reward": 0, "error": "bad supervisor invocation"})
        return 0

    python_bin_arg = Path(sys.argv[1])
    python_bin = python_bin_arg.resolve()
    verifier = Path(sys.argv[2]).resolve()
    workdir = Path(sys.argv[3]).resolve()
    success_token = sys.argv[4]
    timeout_sec = int(sys.argv[5])
    for path in (python_bin, verifier, Path(__file__).resolve()):
        reason = trusted_regular_file(path)
        if reason is not None:
            write_reward(0, {"reward": 0, "error": reason})
            return 0

    env = {name: os.environ[name] for name in ENV_PASSTHROUGH if name in os.environ}
    command = [str(python_bin_arg), "-I", str(verifier)]
    setpriv = Path("/usr/bin/setpriv")
    try:
        agent = pwd.getpwnam("agent")
    except KeyError:
        agent = None
    if agent is not None and setpriv.exists():
        command = [
            str(setpriv),
            f"--reuid={agent.pw_uid}",
            f"--regid={agent.pw_gid}",
            "--clear-groups",
            "--no-new-privs",
            *command,
        ]
        env["HOME"] = agent.pw_dir

    try:
        result = subprocess.run(
            command,
            cwd=str(workdir),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        LOG.write_text(output if isinstance(output, str) else output.decode())
        write_reward(0, {"reward": 0, "error": "timeout"})
        return 0

    LOG.write_text(result.stdout)
    print(result.stdout, end="")
    passed = result.returncode == 0 and success_token in result.stdout
    write_reward(
        1 if passed else 0,
        {
            "reward": 1 if passed else 0,
            "child_exit_code": result.returncode,
            "success_token_seen": success_token in result.stdout,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
