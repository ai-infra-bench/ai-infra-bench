#!/usr/bin/env python3
"""Root scorer: drive and validate every operation outside candidate Python."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import secrets
import signal
import socket
import stat
import subprocess
import sys
import time

# -I intentionally omits the script directory. It is a root-owned staging path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_connector_lifecycle import verify

ROOT = Path("/logs/verifier")


def trusted(path):
    info = path.stat()
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022:
        raise RuntimeError(f"untrusted verifier executable: {path}")


def write_result(payload):
    for name, data in (("behavior-report.json", json.dumps(payload, indent=2) + "\n"),
                       ("reward.json", json.dumps({"reward": payload["reward"]}) + "\n"),
                       ("reward.txt", str(payload["reward"]) + "\n")):
        fd = os.open(ROOT / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w") as out:
            os.fchown(out.fileno(), 0, 0)
            os.fchmod(out.fileno(), 0o644)
            out.write(data)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "observations.jsonl").write_text("")
    result = {"reward": 0, "completed_checks": [], "operations": 0}
    child = None
    parent = peer = None
    started = time.monotonic()
    try:
        if os.geteuid() != 0 or len(sys.argv) != 4:
            raise RuntimeError("expected root supervisor: python workdir timeout")
        python = Path(sys.argv[1])
        stage = Path(__file__).resolve().parent
        for path in (python.resolve(), Path(__file__).resolve(),
                     stage / "verify_connector_lifecycle.py", stage / "connector_worker.py"):
            trusted(path)
        agent = pwd.getpwnam("agent")
        if agent.pw_uid == 0:
            raise RuntimeError("candidate user must be unprivileged")
        deadline = started + float(sys.argv[3])
        parent, peer = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": agent.pw_dir,
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
               "PYTHONUNBUFFERED": "1"}
        # Runtime search paths only; never propagate Python hooks or LD_PRELOAD.
        for name in ("LD_LIBRARY_PATH", "LANG", "LC_ALL"):
            if name in os.environ:
                env[name] = os.environ[name]
        command = ["/usr/bin/setpriv", f"--reuid={agent.pw_uid}", f"--regid={agent.pw_gid}",
                   "--clear-groups", "--no-new-privs", str(python), "-I",
                   str(stage / "connector_worker.py"), str(peer.fileno()), sys.argv[2]]
        with (ROOT / "candidate.log").open("w") as log:
            child = subprocess.Popen(command, cwd=sys.argv[2], env=env,
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     pass_fds=(peer.fileno(),), start_new_session=True)
            peer.close()
            peer = None

            def receive():
                parent.settimeout(max(0.01, deadline - time.monotonic()))
                packet = parent.recv(1 << 20)
                if not packet:
                    raise RuntimeError("candidate exited before the required operation completed")
                return json.loads(packet)

            if receive() != {"ready": True}:
                raise RuntimeError("candidate failed to initialize the behavioral adapter")

            def call(**command):
                command["id"] = secrets.token_hex(16)
                parent.send(json.dumps(command).encode())
                response = receive()
                if not isinstance(response, dict) or set(response) != {"id", "value", "error", "events"}:
                    raise RuntimeError("invalid operation response")
                if response["id"] != command["id"]:
                    raise RuntimeError("response did not match the pending operation")
                result["operations"] += 1
                # The parent records observations and independently checks them.
                trace.write(json.dumps({"request": command, "observation": response}) + "\n")
                trace.flush()
                return response

            with (ROOT / "observations.jsonl").open("w") as trace:
                verify(call, result["completed_checks"])
            parent.shutdown(socket.SHUT_WR)
            code = child.wait(timeout=max(0.01, deadline - time.monotonic()))
            if code != 0:
                raise RuntimeError(f"candidate failed after the final operation: exit {code}")
            result["reward"] = 1
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if parent is not None:
            parent.close()
        if peer is not None:
            peer.close()
        if child is not None:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            result["child_exit_code"] = child.returncode
        result["duration_sec"] = round(time.monotonic() - started, 3)
        write_result(result)
        text = json.dumps(result, indent=2)
        (ROOT / "verifier.log").write_text(text + "\n")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
