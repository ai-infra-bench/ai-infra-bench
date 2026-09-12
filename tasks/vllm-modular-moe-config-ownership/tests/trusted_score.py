"""Trusted grading parent. Start with -I -S: never execute candidate startup code."""
import ctypes
import json
import os
from pathlib import Path
import pwd
import secrets
import subprocess
import sys
import sysconfig
import tempfile
import traceback

sys.path.insert(0, "/tests")
from check_behavior import EXPECTED_STAGES, check
from workload import make_workload


def unprivileged():
    account = pwd.getpwnam("agent")
    os.setgroups([])
    os.setgid(account.pw_gid)
    os.setuid(account.pw_uid)
    ctypes.CDLL(None).prctl(38, 1, 0, 0, 0)  # no_new_privs


def main():
    log = Path("/logs/verifier")
    log.mkdir(parents=True, exist_ok=True)
    os.chown(log, 0, 0)
    os.chmod(log, 0o755)
    for name in ("reward.txt", "reward.json", "report.json"):
        (log / name).unlink(missing_ok=True)
    (log / "reward.txt").write_text("0\n")
    # The parent retains the authoritative inputs in memory. Child-provided
    # input descriptions cannot substitute a different, self-consistent test.
    sys.path.extend([sysconfig.get_path("purelib"), sysconfig.get_path("platlib")])
    seed = secrets.randbits(63)
    workload = make_workload(seed)
    workload_path = log / "workload.json"
    workload_path.write_text(json.dumps(workload))
    os.chmod(workload_path, 0o444)
    account = pwd.getpwnam("agent")
    obs_dir = Path(tempfile.mkdtemp(prefix="behavior-observations-"))
    os.chown(obs_dir, account.pw_uid, account.pw_gid)
    obs = obs_dir / "observations.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("AIB_") and k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(AIB_OBSERVATIONS=str(obs), AIB_SEED=str(seed), AIB_WORKLOAD=str(workload_path), PYTHONDONTWRITEBYTECODE="1")
    # FlashInfer initializes its ordinary JIT cache on import. The worker runs
    # as agent, so place that cache in its writable per-run directory.
    env["FLASHINFER_WORKSPACE_BASE"] = str(obs_dir)
    # Paths are added explicitly; site .pth and sitecustomize are never run.
    bootstrap = "import runpy,sys; sys.path.extend(" + repr(["/workspace/repo","/tests",sysconfig.get_path("purelib"),sysconfig.get_path("platlib")]) + "); runpy.run_path(sys.argv[1],run_name='__main__')"
    result = subprocess.run([sys.executable, "-I", "-S", "-c", bootstrap, sys.argv[1]],
                            env=env, cwd="/workspace/repo", preexec_fn=unprivileged,
                            timeout=1050)
    passed, failures = [], []
    try:
        if result.returncode != 0:
            raise RuntimeError(f"candidate worker exit {result.returncode}")
        if obs.stat().st_size > 100_000_000:
            raise ValueError("observation size limit exceeded")
        raw = json.loads(obs.read_text())
        (log / "observations.json").write_text(json.dumps(raw))
        # Only installed, root-owned numerical dependencies are loaded here.
        sys.path.extend([sysconfig.get_path("purelib"), sysconfig.get_path("platlib")])
        passed = check(raw, workload)
        assert set(passed) == set(EXPECTED_STAGES) and len(passed) == len(EXPECTED_STAGES)
    except Exception:
        failures.append(traceback.format_exc())
        print(failures[-1], flush=True)
    report = {"schema_version": "trusted_behavior_report.v1", "completed": not failures,
              "expected_stages": EXPECTED_STAGES, "stages_passed": passed,
              "failures": failures, "worker_exit_code": result.returncode,
              "worker_uid": account.pw_uid, "scorer_uid": os.getuid()}
    (log / "report.json").write_text(json.dumps(report, indent=2)+"\n")
    reward = int(not failures)
    (log / "reward.json").write_text(json.dumps({"reward": reward, "verifier_exit_code": result.returncode})+"\n")
    (log / "reward.txt").write_text(str(reward)+"\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
