"""Apply a source submission in a fresh verifier and validate completed results."""
from collections import Counter
import ctypes
import json
import os
from pathlib import Path
import signal
import stat
import subprocess

tests = Path(__file__).resolve().parent
root = Path(os.environ.get("DSH_ROOT", "/workspace/deepseek-harness"))
logs = Path(os.environ.get("DSH_LOGS", "/logs/verifier"))
logs.mkdir(parents=True, exist_ok=True)
logs.chmod(0o700)
report = logs / "results.json"
report.unlink(missing_ok=True)
(logs / "reward.txt").write_text("0\n")
(logs / "reward.json").unlink(missing_ok=True)
reward = 0
reason = "verifier did not complete"
code = None
process_code = None


def no_new_privileges():
    # Inherited by the runner and its unprivileged test workers.
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")


def builder_identity():
    no_new_privileges()
    os.setgroups([])
    os.setgid(65534)
    os.setuid(65534)


def source_owner(uid):
    """Change only source/build files; never follow candidate-created links."""
    for base, dirs, files, fd in os.fwalk(root, follow_symlinks=False):
        dirs[:] = [name for name in dirs if name not in {".git", "node_modules"}]
        if Path(base) != root:
            os.fchown(fd, uid, uid)
            os.fchmod(fd, 0o755)
        for name in files:
            try:
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            except OSError:
                continue
            try:
                info = os.fstat(child)
                if stat.S_ISREG(info.st_mode):
                    os.fchown(child, uid, uid)
                    os.fchmod(child, (stat.S_IMODE(info.st_mode) & 0o111) | 0o644)
            finally:
                os.close(child)


def build_candidate(env):
    # The image contains Base's normal web/client assets. Rebundle candidate
    # host modules so the actual CLI never tests stale Base library output.
    source_owner(65534)
    child = None
    try:
        with (logs / "build.log").open("w") as stream:
            child = subprocess.Popen(
                [str(root / "node_modules/.bin/tsdown"), "--env.DSH_BUILD_FACE", "host"],
                cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
                preexec_fn=builder_identity, start_new_session=True,
            )
            status = child.wait(timeout=240)
        if status != 0:
            raise ValueError(f"candidate host bundling failed: {status}")
    finally:
        if child is not None:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
        source_owner(0)


def apply_submission():
    """Do not transfer agent-owned executables, dependencies, Git state or links."""
    patch = Path("/tmp/benchmark-submission/submission.patch")
    if not patch.is_file() or patch.is_symlink():
        raise ValueError("missing regular submission patch")
    if patch.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("submission patch exceeds 16 MiB")
    if patch.stat().st_size == 0:
        return
    result = subprocess.run(
        ["/usr/bin/git", "apply", "--numstat", "-z", str(patch)],
        cwd=root, check=True, capture_output=True,
    )
    records = iter(result.stdout.split(b"\0"))
    for record in records:
        if not record:
            continue
        name = record.split(b"\t", 2)[2]
        names = [name] if name else [next(records), next(records)]
        for raw in names:
            path = Path(os.fsdecode(raw))
            if path.is_absolute() or any(p in {"..", ".git", "node_modules"} for p in path.parts):
                raise ValueError("submission attempts to replace verifier infrastructure")
    # Refresh inode/mtime cache entries copied through Docker image layers.
    subprocess.run(["/usr/bin/git", "update-index", "--refresh"], cwd=root, check=True)
    # A fresh Git index enforces normal path/symlink safety during application.
    subprocess.run(["/usr/bin/git", "apply", "--index", str(patch)], cwd=root, check=True)
    changes = subprocess.check_output(["/usr/bin/git", "diff", "--cached", "--raw", "-z"], cwd=root)
    for record in changes.split(b"\0"):
        if record.startswith(b":") and record.split()[1] in {b"120000", b"160000"}:
            raise ValueError("submission introduces a symbolic link or submodule")


try:
    if os.getuid() != 0:
        raise ValueError("the isolated verifier parent must run as root")
    apply_submission()
    expected = Counter(json.loads((tests / "expected-tests.json").read_text()))
    env = dict(PATH="/usr/local/bin:/usr/bin:/bin", HOME="/tmp", LANG="C.UTF-8",
               DSH_REPORT=str(report), DSH_ROOT=str(root), CI="true")
    build_candidate(env)
    with (logs / "vitest.log").open("w") as stream:
        result = subprocess.run(
            ["/usr/local/bin/node", str(root / "node_modules/vitest/vitest.mjs"), "run", "--configLoader", "native", "--config", str(tests / "vitest.config.mjs")],
            cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=480,
            preexec_fn=no_new_privileges,
        )
    code = result.returncode
    data = json.loads(report.read_text())
    suites = data["testResults"]
    assertions = [case for suite in suites for case in suite["assertionResults"]]
    actual = Counter(case["fullName"] for case in assertions)
    complete = actual == expected and all(case["status"] == "passed" for case in assertions)
    success = (
        code == 0 and complete and data["success"] is True
        and data["numTotalTests"] == sum(expected.values())
        and data["numPassedTests"] == sum(expected.values())
        and data["numFailedTests"] == 0 and data["numPendingTests"] == 0
        and data.get("numTodoTests", 0) == 0
        and all(suite["status"] == "passed" for suite in suites)
    )
    process_expected = json.loads((tests / "expected-process-cases.json").read_text())
    process_out = logs / "process"
    with (logs / "process.log").open("w") as stream:
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(tests / "process/run.py"),
             "--root", str(root), "--out", str(process_out),
             "--cases", ",".join(process_expected)],
            cwd="/tmp", env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=420,
        )
    process_code = result.returncode
    process_results = json.loads((process_out / "results.json").read_text())
    process_complete = (
        process_code == 0
        and Counter(item["case"] for item in process_results) == Counter(process_expected)
        and all(item["status"] == "passed" for item in process_results)
    )
    reward = int(success and process_complete)
    reason = "all required unit and process cases passed" if reward else "failed, skipped, or incomplete unit/process cases"
except (OSError, ValueError, KeyError, TypeError, IndexError, StopIteration, subprocess.SubprocessError) as error:
    reason = f"incomplete verification: {type(error).__name__}: {error}"
finally:
    (logs / "reward.txt").write_text(f"{reward}\n")
    details = {"reward": reward, "child_exit_code": code, "process_exit_code": process_code, "reason": reason}
    (logs / "grading-details.json").write_text(json.dumps(details, indent=2) + "\n")
    print(json.dumps(details))
