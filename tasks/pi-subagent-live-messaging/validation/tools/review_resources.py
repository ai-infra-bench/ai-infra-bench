#!/usr/bin/env python3
"""Source-reviewed resource/fault probes, separate from generic Harbor scoring.

A curator supplies a profile with source_sha256 for the reviewed implementation,
and kind=file-mailbox|tcp|unix|native-ipc. File profiles additionally specify
team_glob and (for mailboxes) members_file. These are review observations, not
candidate APIs. New source bytes require renewed review and a new profile.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time


def tcp_query(port, local=None, destroy=False):
    command = ["ss", "-H", "-n", "-t"]
    if local is None:
        command += ["-l", "sport", "=", str(port)]
    else:
        if destroy:
            command.append("-K")
        command += ["state", "established", "src", "127.0.0.1", "sport", "=", str(local),
                    "dst", "127.0.0.1", "dport", "=", str(port)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
    return {"command": command, "stdout": result.stdout, "stderr": result.stderr}


def check_profile(repo, profile):
    assert profile["kind"] in {"file-mailbox", "tcp", "unix", "native-ipc"}
    hashes = profile["source_sha256"]
    assert hashes, "profile must pin the source that was actually reviewed"
    for relative, expected in hashes.items():
        path = (repo / relative).resolve()
        assert path.is_relative_to(repo), "source path escapes checkout"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f"unreviewed source: {relative}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["fault", "cleanup"], required=True)
    parser.add_argument("--node", default="/usr/local/bin/node")
    args = parser.parse_args()
    assert os.geteuid() == 0, "run with the same root/UID-60000 separation as the behavioral verifier"
    repo = args.repo.resolve()
    profile = json.loads(args.profile.read_text())
    check_profile(repo, profile)
    kind = profile["kind"]
    if args.mode == "fault":
        assert kind in {"file-mailbox", "tcp"}, "use public queue-pressure coverage for native IPC; no unsupported fault simulation"
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "source-profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    tests = Path(__file__).resolve().parents[2] / "tests"
    # The local review may use a source checkout outside /workspace/pi. Record
    # these two path substitutions; never describe such a run as image/Harbor CI.
    with tempfile.TemporaryDirectory(prefix="pi-resource-harness-") as temporary:
        harness = Path(temporary)
        harness.chmod(0o755)
        for name in ["verify.py", "fixture.ts", "worker_exec.py"]:
            data = (tests / name).read_text()
            if name == "verify.py":
                data = data.replace('"/usr/local/bin/node"', json.dumps(args.node))
            if name == "fixture.ts":
                data = data.replace("/workspace/pi", str(repo))
            (harness / name).write_text(data)
            (harness / name).chmod(0o644)
        shutil.copytree(harness, args.output / "harness")
        spec = importlib.util.spec_from_file_location("resource_verify", harness / "verify.py")
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)

        class ResourceCase(verify.Case):
            def __init__(self, name):
                super().__init__(name)
                self.paths = set()
                self.ports = set()
                self.original_mode = None
                self.mailbox = None
                self.fault_evidence = None

            def observe_resources(self):
                if kind in {"file-mailbox", "unix"}:
                    pattern = profile["team_glob"]
                    assert "/" not in pattern and pattern != "*", "use the source-reviewed team directory prefix"
                    for directory in (self.scratch / "tmp").glob(pattern):
                        assert not directory.is_symlink() and directory.is_dir()
                        if kind == "file-mailbox":
                            members = json.loads((directory / profile["members_file"]).read_text())
                            assert {m["id"] for m in members} == set(self.ids.values()), "directory is not this dispatch"
                        else:
                            assert any(stat.S_ISSOCK(p.lstat().st_mode) for p in directory.iterdir()), "reviewed Unix endpoint absent"
                        self.paths.add(directory)
                elif kind == "tcp":
                    for event in self.events:
                        if event["event"].startswith("tool_start:"):
                            self.ports.update(s["remotePort"] for s in event.get("sockets", []))

            def inject_fault(self):
                self.observe_resources()
                if kind == "file-mailbox":
                    assert len(self.paths) == 1, "mailbox team not uniquely located"
                    directory = next(iter(self.paths))
                    self.mailbox = directory / hashlib.sha256(self.ids["C"].encode()).hexdigest()
                    fd = os.open(self.mailbox, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try:
                        self.original_mode = stat.S_IMODE(os.fstat(fd).st_mode)
                        os.fchmod(fd, 0o500)
                    finally:
                        os.close(fd)
                    self.fault_evidence = {"recipient": "C", "operation": "deny writes to reviewed mailbox", "path": str(self.mailbox)}
                else:
                    def connection(role):
                        entries = [e for e in self.events if e["role"] == role and e["event"] == "tool_start:slow_work"]
                        assert len(entries) == 1 and len(entries[0]["sockets"]) == 1, "reviewed TCP connection not uniquely located"
                        return entries[0]["sockets"][0]
                    b, c = connection("B"), connection("C")
                    assert b["remotePort"] == c["remotePort"] and b["localPort"] != c["localPort"]
                    before = tcp_query(c["remotePort"], c["localPort"])
                    assert len(before["stdout"].splitlines()) == 1, "expected exactly C's existing connection"
                    reset = tcp_query(c["remotePort"], c["localPort"], destroy=True)
                    after = tcp_query(c["remotePort"], c["localPort"])
                    peer = tcp_query(b["remotePort"], b["localPort"])
                    assert not after["stdout"].strip() and peer["stdout"].strip(), "C was not reset independently of B"
                    self.fault_evidence = {"recipient": "C", "before": before, "reset": reset, "after": after, "B_unchanged": peer}
                self.event("one", "A", "real_transport_fault", evidence=self.fault_evidence)

            def work(self, group, role, stage):
                if stage == "fault_prepared":
                    return "Continue the investigation."
                self.observe_resources()
                value = super().work(group, role, stage)
                if args.mode == "fault" and role == "A" and stage == "ready":
                    self.inject_fault()
                if role == "C" and stage == "slow_work" and self.mailbox is not None:
                    self.mailbox.chmod(self.original_mode)
                    self.mailbox = None
                return value

            def respond(self, body, pid):
                response = super().respond(body, pid)
                # Reuse the broadcast result/recipient checks, without the 66
                # capacity-fill sends. The actual failure comes from the OS.
                if args.mode == "fault" and self.prefill_calls:
                    self.prefill_calls.clear()
                    return self.call("test_work", {"stage": "fault_prepared"})
                return response

        def cleanup_observer(case, scratch):
            assert args.mode == "cleanup"
            observed = bool(case.paths or case.ports or (kind == "native-ipc" and case.pids))
            def remaining():
                paths = [str(p) for p in case.paths if p.exists()]
                listeners = [p for p in case.ports if tcp_query(p)["stdout"].strip()]
                return {"paths": paths, "listeners": listeners}
            deadline = time.monotonic() + 6
            resources = remaining()
            while any(resources.values()) and time.monotonic() < deadline:
                time.sleep(0.05)
                resources = remaining()
            return {"passed": observed and not any(resources.values()), "observed_paths": sorted(map(str, case.paths)),
                    "observed_listener_ports": sorted(case.ports), "remaining": resources,
                    "basis": "source-reviewed dispatch resources; observed before verifier teardown"}

        results = []
        names = ["transport_fault"] if args.mode == "fault" else ["cancellation", "cancel_queued"]
        for name in names:
            case = ResourceCase("broadcast_pressure" if args.mode == "fault" else name)
            result = verify._run_case(name, repo, args.output, case,
                                      cleanup_observer=cleanup_observer if args.mode == "cleanup" else None)
            if args.mode == "fault":
                outcomes = [e for e in case.events if e["event"] == "pressure_broadcast_result"]
                partial = len(outcomes) == 1 and outcomes[0]["accepted"] == ["B"] and outcomes[0]["failed"] == ["C"]
                result["fault_review"] = {"passed": bool(case.fault_evidence) and partial,
                                           "injection": case.fault_evidence, "outcomes": outcomes}
            result["review_passed"] = result["passed"] and result.get("resource_review", result.get("fault_review", {})).get("passed", False)
            results.append(result)
        summary = {"kind": kind, "mode": args.mode, "passed": all(r["review_passed"] for r in results),
                   "scope": "source-reviewed supplementary validation, not generic Harbor reward",
                   "node": args.node, "repo": str(repo), "results": results}
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({k: summary[k] for k in ["kind", "mode", "passed", "scope"]}))
        return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
