"""Score public results against an independent, fresh model execution."""

import ctypes
import json
import os
from pathlib import Path
import pwd
import secrets
import signal
import subprocess
import sys
import sysconfig
import tempfile
import traceback

sys.path.insert(0, "/tests")
sys.path.extend([sysconfig.get_path("purelib"), sysconfig.get_path("platlib")])
from reference import AmbiguousReference, build_reference, check_results


def unprivileged():
    account = pwd.getpwnam("agent")
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    ctypes.CDLL(None).prctl(38, 1, 0, 0, 0)


def main():
    log = Path("/logs/verifier")
    log.mkdir(parents=True, exist_ok=True)
    os.chmod(log, 0o755)
    for name in ("reward.txt", "reward.json", "report.json", "observations.json"):
        (log / name).unlink(missing_ok=True)
    (log / "reward.txt").write_text("0\n")
    failures, passed, workload = [], [], {}
    worker_exit = None
    seed = None
    reference_attempts = 0
    try:
        model = Path(tempfile.mkdtemp(prefix="session-model-"))
        for attempt in range(5):
            reference_attempts = attempt + 1
            seed = secrets.randbits(63)
            try:
                workload, expected = build_reference(model, seed)
                break
            except AmbiguousReference:
                if attempt == 4:
                    raise
        model.chmod(0o755)
        for path in model.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
        workload_path = log / "workload.json"
        workload_path.write_text(json.dumps(workload))
        workload_path.chmod(0o444)
        private = Path(tempfile.mkdtemp(prefix="session-reference-"))
        (private / "expected.json").write_text(json.dumps(expected))
        account = pwd.getpwnam("agent")
        scratch = Path(tempfile.mkdtemp(prefix="session-worker-"))
        os.chown(scratch, account.pw_uid, account.pw_gid)
        scratch.chmod(0o700)
        observations = scratch / "observations.json"
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("AIB_") and key not in ("PYTHONPATH", "PYTHONHOME")}
        env.update(
            AIB_MODEL=str(model), AIB_WORKLOAD=str(workload_path),
            AIB_OBSERVATIONS=str(observations), VLLM_NO_USAGE_STATS="1",
            FLASHINFER_WORKSPACE_BASE=str(scratch / "flashinfer"),
            TORCHINDUCTOR_CACHE_DIR=str(scratch / "inductor"),
            TRITON_CACHE_DIR=str(scratch / "triton"), XDG_CACHE_HOME=str(scratch / "cache"),
            XDG_CONFIG_HOME=str(scratch / "config"), PYTHONDONTWRITEBYTECODE="1",
        )
        bootstrap = (
            "import runpy,sys,sysconfig; sys.path.extend("
            + repr(["/workspace/repo", "/tests", sysconfig.get_path("purelib"),
                    sysconfig.get_path("platlib")])
            + "); runpy.run_path(sys.argv[1],run_name='__main__')"
        )
        with (log / "worker.log").open("w") as output:
            child = subprocess.Popen(
                [sys.executable, "-I", "-S", "-c", bootstrap,
                 "/tests/verify_streaming_public_api.py"],
                env=env, cwd="/workspace/repo", preexec_fn=unprivileged,
                start_new_session=True, stdout=output, stderr=subprocess.STDOUT,
            )
            try:
                worker_exit = child.wait(timeout=1020)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        if worker_exit != 0:
            raise RuntimeError(f"public behavior worker exited {worker_exit}; see worker.log")
        if observations.stat().st_size > 2_000_000:
            raise ValueError("oversized public observations")
        raw = json.loads(observations.read_text())
        passed = check_results(raw, workload, expected)
        (log / "observations.json").write_text(json.dumps(raw))
    except BaseException:
        failures.append(traceback.format_exc())
    report = {
        "schema_version": "independent_session_behavior.v1", "completed": not failures,
        "expected_cases": list(workload.get("cases", {})), "cases_passed": passed,
        "failures": failures, "worker_exit_code": worker_exit,
        "reference_seed": seed,
        "reference_attempts": reference_attempts,
    }
    (log / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    reward = int(not failures)
    (log / "reward.json").write_text(json.dumps({"reward": reward}) + "\n")
    (log / "reward.txt").write_text(f"{reward}\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
