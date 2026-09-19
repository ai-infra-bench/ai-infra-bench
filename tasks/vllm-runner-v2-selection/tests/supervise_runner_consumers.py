#!/usr/bin/env python3
"""Parent-owned grading; stdout is diagnostic, never evidence of completion.

The preloaded suite authenticates checkpoint events from its original code
object over an inherited channel. This blocks report-only and early-exit
controls. In-process Python instrumentation is not an arbitrary-code sandbox.
"""
from __future__ import annotations

import hmac
import json
import os
import pwd
import runpy
import secrets
import importlib.util
import select
import signal
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REWARD = Path("/logs/verifier/reward.txt")
PLUGIN = "vllm.v1.sample.logits_processor.builtin:MinPLogitsProcessor"


def case(name, expected, override=None, **options):
    return dict(name=name, expected=expected, override=override, **options)


CASES = [
    case("auto_qwen3", "V2"),
    case("auto_qwen2", "V1", model="qwen2"),
    case("auto_pooling", "V1", model_options={"runner": "pooling"}),
    case("auto_quantized", "V1", model="qwen3-fp8"),
    case("auto_moe", "V1", model="qwen3-moe"),
    case("auto_kv_sharing", "V1", kv_sharing=True),
    case("auto_logits_processor", "V1", model_options={"logits_processors": [PLUGIN]}),
    case("auto_prompt_embeds", "V1", model_options={"enable_prompt_embeds": True}),
    case("auto_raw_logits", "V1", model_options={"logprobs_mode": "raw_logits"}),
    case("auto_processed_logits", "V1", model_options={"logprobs_mode": "processed_logits"}),
    case("forced_v1", "V1", "0"),
    case("forced_v1_kv_sharing", "V1", "0", kv_sharing=True),
    case("forced_v1_raw_logits", "V1", "0", model_options={"logprobs_mode": "raw_logits"}),
    case("forced_v2", "V2", "1"),
    case("forced_v2_qwen2", "V2", "1", model="qwen2"),
    case("reject_kv_sharing", "reject", "1", kv_sharing=True),
    case("reject_logits_processor", "reject", "1", model_options={"logits_processors": [PLUGIN]}),
    case("reject_prompt_embeds", "reject", "1", model_options={"enable_prompt_embeds": True}),
    case("reject_raw_logits", "reject", "1", model_options={"logprobs_mode": "raw_logits"}),
    case("reject_processed_logits", "reject", "1", model_options={"logprobs_mode": "processed_logits"}),
    # Pooling support is narrower than the set of valid V1 configurations.
    case('pool_last', 'V2', '1', model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'LAST', 'use_activation': True}}),
    case('pool_mean', 'reject', '1', model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'MEAN', 'use_activation': True}}),
    case('pool_cls', 'reject', '1', model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'CLS', 'use_activation': True}}),
    case('pool_unnormalized', 'reject', '1', model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'LAST', 'use_activation': False}}),
    case('pool_auto_mean', 'V1', None, model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'MEAN', 'use_activation': True}}),
    case('pool_forced_v1_mean', 'V1', '0', model_options={'runner': 'pooling', 'convert': 'embed', 'pooler_config': {'pooling_type': 'MEAN', 'use_activation': True}}),
    # Repeat an automatic startup with a fresh configuration.
    case("auto_repeat", "V2"),
]


def trusted(path):
    info = path.stat()
    return info.st_uid == 0 and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022


def reward(value):
    fd = os.open(REWARD, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    try:
        os.fchown(fd, 0, 0)
        os.fchmod(fd, 0o644)
        os.write(fd, f"{value}\n".encode())
    finally:
        os.close(fd)


def grade(spec, observation):
    error = observation.get("error")
    if spec["expected"] == "reject":
        # The paired compatible cases must start. An incompatible case must
        # reject before startup completes, with a diagnostic. No prescribed
        # exception subclass, helper, validation phase or English vocabulary.
        return observation.get("runner") is None and isinstance(error, dict) and bool(str(error.get("message", "")).strip())
    return error is None and observation.get("runner") == spec["expected"]


def main():
    if os.geteuid() != 0:
        raise RuntimeError("the scoring parent must run as root")
    REWARD.parent.mkdir(parents=True, exist_ok=True)
    os.chown(REWARD.parent, 0, 0)
    REWARD.parent.chmod(0o755)
    if REWARD.is_symlink():
        REWARD.unlink()
    reward(0)
    python = Path(sys.argv[1])
    worker_file = HERE / "verify_runner_consumers.py"
    for path in (python, python.resolve(), Path(__file__), worker_file):
        if not trusted(path):
            raise RuntimeError(f"untrusted harness file: {path}")
    # Independent preflight: candidate imports cannot fabricate CUDA presence.
    subprocess.run(
        [str(python), "-I", "-c", "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'"],
        cwd=str(HERE), check=True, timeout=45,
    )
    groups = [[c for c in CASES if c["override"] == value] for value in (None, "0", "1")]
    (REWARD.parent / "worker.log").write_bytes(b"")
    deadline = time.monotonic() + 480
    for group in groups:
        if not run_group(python, group, deadline):
            return 0
    reward(1)
    return 0


def run_group(python, cases, deadline):
    worker_file = HERE / "verify_runner_consumers.py"
    extension = HERE / "_checkpoint.so"
    if not trusted(extension):
        raise RuntimeError("untrusted checkpoint extension")
    spec = importlib.util.spec_from_file_location("_checkpoint", extension)
    checkpoint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checkpoint)
    suite = runpy.run_path(str(worker_file))["run_suite"]
    account = pwd.getpwnam("agent")
    key = secrets.token_bytes(32)
    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
    log = open(REWARD.parent / "worker.log", "ab", buffering=0)
    pid = os.fork()
    if pid == 0:
        try:
            parent.close()
            checkpoint.configure(key, child.fileno(), suite.__code__, json.dumps)
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
            os.environ.update(HOME=account.pw_dir, XDG_CACHE_HOME=account.pw_dir + "/.cache", PYTHONPATH="/workspace/repo", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", VLLM_NO_USAGE_STATS="1")
            Path(account.pw_dir, ".cache").mkdir(exist_ok=True)
            os.chdir("/workspace/repo")
            override = cases[0]["override"]
            if override is None:
                os.environ.pop("VLLM_USE_V2_MODEL_RUNNER", None)
            else:
                os.environ["VLLM_USE_V2_MODEL_RUNNER"] = override
            suite(cases, checkpoint.emit)
            child.close()
            os._exit(0)
        except BaseException:
            import traceback
            traceback.print_exc()
            os._exit(1)
    child.close()
    log.close()
    accepted = 0
    previous = b""
    failures = []
    exit_status = None
    try:
        while accepted < len(cases):
            if time.monotonic() >= deadline:
                failures.append("suite timed out before completing all checkpoints")
                break
            readable, _, _ = select.select([parent], [], [], 0.2)
            if readable:
                packet = parent.recv(65536)
                signature, body = packet[:32], packet[32:]
                if not hmac.compare_digest(signature, hmac.digest(key, previous + body, "sha256")):
                    failures.append("unauthenticated checkpoint")
                    break
                observed = json.loads(body)
                spec = cases[accepted]
                if observed.get("index") != accepted or observed.get("name") != spec["name"]:
                    failures.append("missing, duplicate or reordered checkpoint")
                    break
                previous = signature
                ok = grade(spec, observed["value"])
                print(f"{'PASS' if ok else 'FAIL'}: {spec['name']}: {observed['value']}", flush=True)
                if not ok:
                    failures.append(spec["name"])
                accepted += 1
            else:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    exit_status = status
                    failures.append(f"worker exited before completed checks ({accepted}/{len(cases)})")
                    break
        if exit_status is None:
            # A complete report is not enough if the worker subsequently hangs.
            until = min(deadline, time.monotonic() + 10)
            while time.monotonic() < until:
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    exit_status = status
                    break
                time.sleep(0.1)
        if exit_status != 0:
            failures.append(f"worker did not finish successfully: {exit_status}")
        print(json.dumps(dict(completed=accepted, required=len(cases), failures=failures)), flush=True)
    finally:
        parent.close()
        if exit_status is None:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(pid, 0)
    return not failures and accepted == len(cases)


if __name__ == "__main__":
    raise SystemExit(main())
