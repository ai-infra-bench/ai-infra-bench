#!/usr/bin/env python3
"""Trusted parent which owns case enumeration, grading, and reward output."""

from __future__ import annotations

import json
import os
import pwd
import secrets
import stat
import subprocess
import sys
from pathlib import Path


REWARD = Path("/logs/verifier/reward.txt")
WORKER = Path(__file__).resolve().with_name("verify_runner_consumers.py")
RESULT_PREFIX = "AI_INFRA_OBSERVATION="

EXPECTED_VALUES: dict[str, object] = {
    "cuda_available": True,
    "qwen3_fixture_available": True,
    "qwen2_fixture_available": True,
    "explicit_zero_accessor": False,
    "explicit_one_accessor": True,
    "auto_dense_qwen3_worker_v2": True,
    "auto_other_arch_worker_v1": False,
    "auto_pooling_worker_v1": False,
    "auto_kv_sharing_worker_v1": False,
    "auto_logits_processor_worker_v1": False,
    "forced_v1_supported_worker_v1": False,
    "forced_v1_unsupported_worker_v1": False,
    "forced_v2_supported_worker_v2": True,
    "forced_v2_other_arch_worker_v2": True,
}
REJECTION_CASES = {
    "forced_v2_kv_sharing_rejected": ("kv sharing", "kv_sharing"),
    "forced_v2_logits_processor_rejected": (
        "logits processor",
        "logits_processors",
    ),
}
CASES = tuple(EXPECTED_VALUES) + ("unset_accessor_readable",) + tuple(REJECTION_CASES)


def write_reward(value: int, *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(REWARD, flags, 0o644)
    try:
        os.fchown(descriptor, 0, 0)
        os.fchmod(descriptor, 0o644)
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def prepare_reward() -> None:
    verifier_dir = REWARD.parent
    try:
        current = verifier_dir.lstat()
    except FileNotFoundError:
        verifier_dir.mkdir(parents=True, mode=0o755)
    else:
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISDIR(current.st_mode):
            verifier_dir.unlink()
            verifier_dir.mkdir(parents=True, mode=0o755)
    os.chown(verifier_dir, 0, 0)
    # Harbor on the host may read/traverse outputs; only root can write.
    verifier_dir.chmod(0o755)
    try:
        REWARD.unlink()
    except FileNotFoundError:
        pass
    write_reward(0, exclusive=True)


def trusted_file(path: Path) -> bool:
    info = path.stat()
    return info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not (
        info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    )


def observation_passes(case: str, value: object) -> tuple[bool, str]:
    if case in EXPECTED_VALUES:
        expected = EXPECTED_VALUES[case]
        return value == expected, f"expected {expected!r}, got {value!r}"
    if case == "unset_accessor_readable":
        valid = isinstance(value, dict) and value.get("value") in (None, False)
        return valid, f"expected an unset-compatible accessor, got {value!r}"
    words = REJECTION_CASES[case]
    valid = isinstance(value, dict) and value.get("rejected") is True
    message = str(value.get("message", "")).lower() if isinstance(value, dict) else ""
    valid = valid and "support" in message and any(word in message for word in words)
    return valid, f"expected explanatory startup rejection, got {value!r}"


def run_case(python_bin: Path, agent: pwd.struct_passwd, case: str) -> tuple[bool, str]:
    nonce = secrets.token_hex(32)
    command = [
        "/usr/bin/setpriv",
        f"--reuid={agent.pw_uid}",
        f"--regid={agent.pw_gid}",
        "--init-groups",
        "--no-new-privs",
        str(python_bin),
        "-I",
        str(WORKER),
    ]
    request = json.dumps({"case": case, "nonce": nonce}) + "\n"
    try:
        result = subprocess.run(
            command,
            cwd="/workspace/repo",
            env={
                **os.environ,
                "PYTHONPATH": "/workspace/repo",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HOME": agent.pw_dir,
                "XDG_CACHE_HOME": f"{agent.pw_dir}/.cache",
            },
            input=request,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "candidate observation process timed out"

    lines = [
        line.removeprefix(RESULT_PREFIX)
        for line in result.stdout.splitlines()
        if line.startswith(RESULT_PREFIX)
    ]
    if result.returncode != 0 or len(lines) != 1:
        return False, (
            "candidate observation did not complete "
            f"(exit={result.returncode}, observations={len(lines)})\n{result.stdout}"
        )
    try:
        observation = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        return False, f"malformed observation: {exc}"
    if (
        observation.get("case") != case
        or observation.get("nonce") != nonce
        or observation.get("error") is not None
    ):
        return False, f"invalid observation envelope: {observation!r}"
    return observation_passes(case, observation.get("value"))


def main() -> int:
    if os.geteuid() != 0:
        print("FAIL: verifier supervisor must run as root")
        return 0
    prepare_reward()
    if len(sys.argv) != 2:
        print("FAIL: trusted Python path was not supplied")
        return 0
    # Preserve the selected venv path for execution; validate its target too.
    python_bin = Path(sys.argv[1])
    python_target = python_bin.resolve()
    supervisor = Path(__file__).resolve()
    for path in (python_bin, python_target, supervisor, WORKER):
        if not trusted_file(path):
            info = path.stat()
            print(
                f"FAIL: untrusted verifier file {path}: "
                f"uid={info.st_uid}, gid={info.st_gid}, "
                f"mode={stat.S_IMODE(info.st_mode):04o}"
            )
            return 0

    agent = pwd.getpwnam("agent")
    completed: list[str] = []
    failures: list[str] = []
    for case in CASES:
        passed, detail = run_case(python_bin, agent, case)
        if passed:
            completed.append(case)
            print(f"PASS: {case}")
        else:
            failures.append(f"{case}: {detail}")
            print(f"FAIL: {failures[-1]}")

    if failures or len(completed) != len(CASES):
        print(f"FAIL: trusted parent completed {len(completed)}/{len(CASES)} cases")
        return 0
    write_reward(1)
    print(f"PASS: trusted parent graded all {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
