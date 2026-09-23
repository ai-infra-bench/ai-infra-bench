#!/usr/bin/python3
"""External Node execution observations. Never import or execute candidate Python.

The CLI and every worker still run candidate code. Inspector observations establish
that the observed processes executed Pi sessions; they are not a proof against an
arbitrary implementation that deliberately runs unrelated sessions as camouflage.
"""
from __future__ import annotations

import base64
import contextlib
from collections import Counter
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import threading
import time
import urllib.request


class InspectorError(RuntimeError):
    pass


def preflight_harness(directory):
    """Reject missing trusted assets before attributing an exit to a candidate."""
    directory = Path(directory)
    for filename in ("fixture.ts", "trusted_faux.mjs", "worker_exec.py"):
        path = directory / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise InspectorError(f"trusted harness asset missing or invalid: {filename}")
        with _process_fsuid():
            try:
                with path.open("rb") as stream:
                    stream.read(1)
            except OSError as exc:
                raise InspectorError(f"trusted harness asset unreadable by Pi: {filename}") from exc
    checked = subprocess.run(["/usr/local/bin/node", "--check", str(directory / "trusted_faux.mjs")],
                             capture_output=True, text=True, timeout=10,
                             env={"PATH": "/usr/local/bin:/usr/bin:/bin"})
    if checked.returncode:
        raise InspectorError("trusted provider syntax check failed: " + checked.stderr[-1000:])


class InspectorSocket:
    """Small stdlib RFC6455 client for Node's local inspector (no extra package)."""
    def __init__(self, url):
        match = re.fullmatch(r"ws://127\.0\.0\.1:(\d+)(/[^\s]*)", url)
        if not match:
            raise InspectorError("inspector must be a local Node endpoint")
        self.sock = socket.create_connection(("127.0.0.1", int(match[1])), timeout=3)
        self.sock.settimeout(3)
        self.pending = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {match[2]} HTTP/1.1\r\nHost: 127.0.0.1:{match[1]}\r\n"
                   f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(request.encode())
        while b"\r\n\r\n" not in self.pending:
            data = self.sock.recv(4096)
            if not data:
                raise InspectorError("inspector closed during handshake")
            self.pending.extend(data)
            if len(self.pending) > 65536:
                raise InspectorError("oversized inspector handshake")
        header, remainder = self.pending.split(b"\r\n\r\n", 1)
        self.pending = bytearray(remainder)
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not header.startswith(b"HTTP/1.1 101 ") or accept not in header:
            raise InspectorError("invalid Node inspector handshake")
        self.sequence = 0
        self.notifications = None
        self.responses = {}

    def _read(self, count):
        while len(self.pending) < count:
            data = self.sock.recv(min(65536, count - len(self.pending)))
            if not data:
                raise EOFError("Node inspector disconnected")
            self.pending.extend(data)
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        header = bytes([0x80 | opcode, 0x80 | min(size, 126)])
        if size >= 65536:
            header = bytes([0x80 | opcode, 0x80 | 127]) + struct.pack("!Q", size)
        elif size >= 126:
            header += struct.pack("!H", size)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _receive(self):
        fragments = bytearray()
        while True:
            first, second = self._read(2)
            size = second & 127
            if size == 126:
                size = struct.unpack("!H", self._read(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._read(8))[0]
            if size > 64 * 1024 * 1024:
                raise InspectorError("oversized inspector observation")
            mask = self._read(4) if second & 128 else None
            payload = self._read(size)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            opcode = first & 15
            if opcode == 8:
                raise EOFError("Node inspector closed")
            if opcode == 9:
                self._send(payload, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise InspectorError("unexpected inspector frame")
            fragments.extend(payload)
            if first & 128:
                return json.loads(fragments)

    def call(self, method, params=None):
        self.sequence += 1
        request_id = self.sequence
        self._send(json.dumps({"id": request_id, "method": method, "params": params or {}}).encode())
        while True:
            result = self.responses.pop(request_id, None)
            if result is None:
                result = self._receive()
            if result.get("id") == request_id:
                if "error" in result:
                    raise InspectorError(result["error"].get("message", str(result["error"])))
                return result.get("result", {})
            if "id" in result:
                self.responses[result["id"]] = result
            elif self.notifications is not None:
                self.notifications(result)

    def close(self):
        with contextlib.suppress(OSError):
            self.sock.close()


@contextlib.contextmanager
def _process_fsuid():
    """Read an unprivileged child's proc links even without CAP_SYS_PTRACE.

    Linux fsuid is per-thread. Restore it before writing root-owned evidence.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    old_gid = libc.setfsgid(60000)
    old = libc.setfsuid(60000)
    try:
        yield
    finally:
        libc.setfsuid(old)
        libc.setfsgid(old_gid)


def process_identity(pid):
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        fields = raw.rsplit(") ", 1)[1].split()
        return {"pid": int(pid), "parent": int(fields[1]), "group": int(fields[2]),
                "start_time": int(fields[19]), "state": fields[0]}
    except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
        return None


def owned_sockets(pid):
    result = set()
    try:
        with _process_fsuid():
            for fd in Path(f"/proc/{pid}/fd").iterdir():
                try:
                    target = os.readlink(fd)
                except (OSError, FileNotFoundError):
                    continue
                match = re.fullmatch(r"socket:\[(\d+)\]", target)
                if match:
                    result.add(match[1])
    except (OSError, FileNotFoundError):
        pass
    return result


def listeners(pid, sockets):
    result = []
    try:
        for line in Path(f"/proc/{pid}/net/tcp").read_text().splitlines()[1:]:
            parts = line.split()
            if parts[3] == "0A" and parts[9] in sockets:
                address, port = parts[1].split(":")
                if address == "0100007F":
                    result.append({"port": int(port, 16), "inode": parts[9]})
    except (OSError, IndexError, ValueError):
        pass
    return result


class RuntimeObserver:
    def __init__(self, root_pid, output_dir, candidate_repo, coordinator_port):
        self.root_pid = int(root_pid)
        self.output_dir = Path(output_dir) / "runtime-observer"
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.repo = str(Path(candidate_repo).resolve())
        self.coordinator_port = int(coordinator_port)
        self.processes = {}
        self.inspections = {}
        self.observed_sockets = set()
        self.errors = []
        self.stop = threading.Event()
        self.forced_stop = threading.Event()
        self.lock = threading.RLock()
        self.threads = []
        self.scan_thread = None
        self._finished = None
        self.provider_requests = Counter()
        self.provider_observations = []
        self.provider_lock = threading.Lock()

    def start(self):
        if self.scan_thread is not None:
            raise RuntimeError("runtime observer already started")
        self.scan_thread = threading.Thread(target=self._scan, daemon=True)
        self.scan_thread.start()
        return self

    def _children(self, pid):
        children = set()
        try:
            for task in Path(f"/proc/{pid}/task").iterdir():
                try:
                    children.update(int(value) for value in (task / "children").read_text().split())
                except (OSError, ValueError):
                    pass
        except OSError:
            pass
        return children

    def _discover(self):
        queue = [self.root_pid, *self.processes]
        seen = set()
        while queue:
            pid = queue.pop()
            if pid in seen:
                continue
            seen.add(pid)
            identity = process_identity(pid)
            if not identity:
                continue
            previous = self.processes.get(pid)
            if previous is not None and previous["start_time"] != identity["start_time"]:
                continue  # Never acquire an unrelated process after PID reuse.
            if previous is None:
                self.processes[pid] = identity
            self.processes[pid]["last_state"] = identity["state"]
            queue.extend(self._children(pid))
            sockets = owned_sockets(pid)
            self.observed_sockets.update(sockets)
            if pid in self.inspections or identity["state"] == "Z":
                continue
            for endpoint in listeners(pid, sockets):
                if endpoint["port"] == self.coordinator_port:
                    continue
                # fork/exec briefly inherits the parent inspector descriptor.
                # Its endpoint still belongs to that parent, never the child.
                if any(item["socket_inode"] == endpoint["inode"] for item in self.inspections.values()):
                    continue
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{endpoint['port']}/json/list", timeout=.2) as response:
                        targets = json.load(response)
                    urls = [target.get("webSocketDebuggerUrl") for target in targets
                            if target.get("type") == "node" and target.get("webSocketDebuggerUrl")]
                    if len(urls) != 1:
                        continue
                except (OSError, ValueError, TypeError):
                    continue  # Other application listeners are not inspector endpoints.
                record = {"pid": pid, "start_time": identity["start_time"], "port": endpoint["port"], "socket_inode": endpoint["inode"],
                          "scripts": {}, "native_prompt": False, "core_executed": False,
                          "resumed": False, "completed": False, "fixture_ready": False, "errors": [], "shutdown_diagnostics": []}
                self.inspections[pid] = record
                thread = threading.Thread(target=self._inspect, args=(urls[0], record), daemon=True)
                self.threads.append(thread)
                thread.start()
                break

    def _scan(self):
        while not self.stop.is_set():
            try:
                with self.lock:
                    self._discover()
            except Exception as exc:
                self.errors.append(f"process discovery: {type(exc).__name__}: {exc}")
                return
            self.stop.wait(.035)

    def _coverage(self, channel, record):
        snapshot = channel.call("Profiler.takePreciseCoverage")
        for script in snapshot.get("result", []):
            url = script.get("url", "")
            if not url.startswith("file://" + self.repo + "/"):
                continue
            called = [function["functionName"] for function in script.get("functions", [])
                      if function.get("ranges") and function["ranges"][0]["count"] > 0]
            if not called:
                continue
            stored = record["scripts"].setdefault(url, set())
            stored.update(called)
            # Observe current public session methods, without replacing their code.
            # A refactor that makes these unavailable is an observation error, not
            # a reason to revert candidate core files to Base.
            if "/packages/coding-agent/src/core/" in url:
                # Import-time evaluation and class static initialization do not
                # establish that a session was ever created or used.
                meaningful = set(called) - {"", "__name", "<static_initializer>"}
                if (url.endswith("/agent-session.ts") and meaningful) or "createAgentSession" in called:
                    record["core_executed"] = True
                if "prompt" in called:
                    record["native_prompt"] = True
        return snapshot

    def _inspect(self, url, record):
        channel = None
        try:
            channel = InspectorSocket(url)
            scripts = {}
            trusted_path = str(Path(__file__).with_name("trusted_faux.mjs").resolve())
            def notification(event):
                params = event.get("params", {})
                if event.get("method") == "Debugger.scriptParsed":
                    scripts[params["scriptId"]] = params.get("url", "")
                elif event.get("method") == "Debugger.paused":
                    try:
                        frames = params.get("callFrames", [])
                        frame = frames[0] if frames else {}
                        if frame and "runtime_pid" not in record:
                            identity = channel.call("Debugger.evaluateOnCallFrame", {
                                "callFrameId": frame["callFrameId"], "expression": "process.pid", "returnByValue": True})
                            record["runtime_pid"] = identity.get("result", {}).get("value")
                            if record["runtime_pid"] != record["pid"]:
                                raise InspectorError("inspector endpoint belongs to a different OS process")
                        url = scripts.get(frame.get("location", {}).get("scriptId"), frame.get("url", ""))
                        if frame.get("functionName") == "observeFixtureReady" and url == "file://" + trusted_path:
                            record["fixture_ready"] = True
                        if frame.get("functionName") == "observeProviderRequest" and url == "file://" + trusted_path:
                            result = channel.call("Debugger.evaluateOnCallFrame", {
                                "callFrameId": frame["callFrameId"], "expression": "payload", "returnByValue": True})
                            payload = result.get("result", {}).get("value")
                            if not isinstance(payload, str):
                                raise InspectorError("trusted provider observation did not return its serialized context")
                            digest = hashlib.sha256(payload.encode()).hexdigest()
                            with self.provider_lock:
                                self.provider_requests[(record["pid"], digest)] += 1
                                self.provider_observations.append({"pid": record["pid"], "sha256": digest})
                    finally:
                        channel.call("Debugger.resume")
            channel.notifications = notification
            channel.call("Debugger.enable")
            channel.call("Profiler.enable")
            channel.call("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
            channel.call("Runtime.runIfWaitingForDebugger")
            record["resumed"] = True
            while not self.stop.is_set():
                self._coverage(channel, record)
                try:
                    response = channel.call("Runtime.evaluate", {"expression": "void 0", "returnByValue": True})
                except InspectorError as exc:
                    if "Cannot find context" in str(exc) or "Execution context was destroyed" in str(exc):
                        record["completed"] = True
                        break
                    raise
                self.stop.wait(.075)
            if not record["completed"]:
                with contextlib.suppress(EOFError, OSError, InspectorError):
                    self._coverage(channel, record)
        except (EOFError, OSError, InspectorError) as exc:
            # Cancellation can terminate a process while a final observation is in
            # flight; already captured evidence remains useful and is retained.
            if self.forced_stop.is_set() and isinstance(exc, (EOFError, ConnectionResetError, BrokenPipeError)):
                record["shutdown_diagnostics"].append(f"after verifier stop: {type(exc).__name__}: {exc}")
            elif process_identity(record["pid"]) is not None and not self.stop.is_set():
                record["errors"].append(f"{type(exc).__name__}: {exc}")
        except Exception as exc:
            record["errors"].append(f"{type(exc).__name__}: {exc}")
        finally:
            if channel is not None:
                channel.close()
            (self.output_dir / f"process-{record['pid']}.json").write_text(
                json.dumps(self._serializable(record), indent=2) + "\n")

    @staticmethod
    def _serializable(record):
        return {**record, "scripts": {name: sorted(functions) for name, functions in record["scripts"].items()}}

    def owns_process(self, pid):
        with self.lock:
            self._discover()
            known = self.processes.get(int(pid))
            current = process_identity(pid)
            return bool(known and current and known["start_time"] == current["start_time"])

    def mark_forced_stop(self):
        """Call immediately before a verifier-owned termination signal.

        Only later channel-close errors caused by shutdown are non-scoring.
        Existing errors, missing execution evidence and leaked processes remain.
        """
        self.forced_stop.set()

    def consume_provider_request(self, pid, raw_body):
        """Bind one HTTP request to its actual protected-provider invocation."""
        digest = hashlib.sha256(raw_body).hexdigest()
        with self.provider_lock:
            key = (int(pid), digest)
            if self.provider_requests[key]:
                self.provider_requests[key] -= 1
                return
        record = self.inspections.get(int(pid))
        if self.errors or (record and record["errors"]):
            raise InspectorError("provider request could not be observed because the runtime observer failed")
        raise AssertionError("model context was not observed in the trusted provider for the reported process")

    def finish(self, actor_pids, cancelled=False):
        if self._finished is not None:
            return self._finished
        self.stop.set()
        if self.scan_thread is not None:
            self.scan_thread.join(timeout=3)
        for thread in self.threads:
            thread.join(timeout=4)
        violations, infrastructure_errors = [], list(self.errors)
        if not self.inspections:
            infrastructure_errors.append("no Node inspector was available for native execution observation")
        if any(thread.is_alive() for thread in self.threads):
            infrastructure_errors.append("runtime inspector did not finish collecting")
        decisive_root_failure = False
        for actor, raw_pid in actor_pids.items():
            label = "/".join(actor) if isinstance(actor, tuple) else str(actor)
            observed = self.inspections.get(int(raw_pid))
            if label.endswith("/ROOT") and observed and observed["resumed"] and not observed["core_executed"] and not observed["errors"]:
                decisive_root_failure = True
        diagnostics = []
        for actor, raw_pid in actor_pids.items():
            pid = int(raw_pid)
            identity = self.processes.get(pid)
            observation = self.inspections.get(pid)
            label = "/".join(actor) if isinstance(actor, tuple) else str(actor)
            if identity is None:
                violations.append(f"{label}: reported Pi process is outside this execution")
            elif observation is None or not observation["resumed"]:
                message = f"{label}: no native execution observation for PID {pid}"
                # A confirmed non-Pi parent can create and kill dummy children too
                # quickly to attach. That missing detail cannot erase the parent's
                # independently established failure.
                (diagnostics if decisive_root_failure else infrastructure_errors).append(message)
            elif observation["errors"]:
                infrastructure_errors.extend(f"{label}: {error}" for error in observation["errors"])
            elif observation["native_prompt"] and not observation["fixture_ready"]:
                infrastructure_errors.append(f"{label}: Pi session ran but trusted fixture did not finish registration")
            elif not observation["native_prompt"]:
                if observation["core_executed"]:
                    infrastructure_errors.append(f"{label}: Pi core ran but public session observation could not be established")
                else:
                    violations.append(f"{label}: no Pi session executed in the reported process")
        if not actor_pids:
            completed_nodes = [item for item in self.inspections.values()
                               if item["resumed"] and not item["errors"]]
            if completed_nodes and all(not item["core_executed"] for item in completed_nodes):
                violations.append("CLI exited without executing a Pi session")
            else:
                infrastructure_errors.append("no actor became ready; trusted fixture/session startup could not be established")
        alive = []
        if cancelled:
            for pid, identity in self.processes.items():
                if pid == self.root_pid:
                    continue
                current = process_identity(pid)
                if current and current["start_time"] == identity["start_time"] and current["state"] != "Z":
                    alive.append(pid)
            if alive:
                violations.append(f"cancelled execution retained child/helper processes: {alive}")
        report = {"passed": not violations and not infrastructure_errors,
                  "violations": violations, "infrastructure_errors": infrastructure_errors, "diagnostics": diagnostics,
                  "processes": list(self.processes.values()),
                  "provider_observations": self.provider_observations,
                  "inspections": [self._serializable(record) for record in self.inspections.values()],
                  "resource_summary": {"observed_socket_inodes": sorted(self.observed_sockets),
                                       "retained_processes": alive},
                  "scope": "external native session execution and process lifetime; not arbitrary-code attestation"}
        (self.output_dir / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        self._finished = report
        return report
