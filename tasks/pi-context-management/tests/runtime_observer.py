"""Bounded external observation of the real Pi CLI; not universal code attestation."""
from __future__ import annotations
import base64
import contextlib
import copy
import ctypes
import gzip
import hashlib
import json
import os
import pwd
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import threading
import time
import urllib.request


class ScoringError(RuntimeError):
    pass


class NoUnusedProviderObservation(ScoringError):
    """An actual HTTP request has no matching public provider-request event."""


InspectorError = ScoringError


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


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        return {"pid": pid, "start_time": int(fields[19]), "state": fields[0]}
    except (OSError, ValueError, IndexError):
        return None


@contextlib.contextmanager
def process_fsuid(pid):
    # Proc fd links require the child's fsuid when root lacks CAP_SYS_PTRACE.
    libc = ctypes.CDLL(None)
    identity = Path(f"/proc/{pid}").stat()
    old_gid = libc.setfsgid(identity.st_gid)
    old_uid = libc.setfsuid(identity.st_uid)
    try:
        yield
    finally:
        libc.setfsuid(old_uid)
        libc.setfsgid(old_gid)


def inspector_endpoint(pid):
    sockets = set()
    with process_fsuid(pid):
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                match = re.fullmatch(r"socket:\[(\d+)\]", os.readlink(fd))
                if match:
                    sockets.add(match[1])
            except OSError:
                pass
    for line in Path(f"/proc/{pid}/net/tcp").read_text().splitlines()[1:]:
        parts = line.split()
        if parts[3] != "0A" or parts[9] not in sockets:
            continue
        address, port = parts[1].split(":")
        if address != "0100007F":
            continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{int(port, 16)}/json/list", timeout=.3) as response:
                targets = json.load(response)
            urls = [target["webSocketDebuggerUrl"] for target in targets if target.get("type") == "node"]
            if len(urls) == 1:
                return urls[0], parts[9]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return None


def same_json(left, right):
    """JSON object order is irrelevant; arrays and scalar JSON types are not."""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(same_json(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


class RuntimeObserver:
    """One CLI PID per phase. HTTP facts are consumed once in parent order."""
    def __init__(self, output_dir, candidate_repo, assets=None):
        self.output_dir = Path(output_dir)
        self.repo = Path(candidate_repo).resolve()
        self.assets = Path(assets or Path(__file__).parent).absolute()
        self.module = self.assets / "context_observation.mjs"
        self.condition = threading.Condition()
        self.facts, self.requests, self.diagnostics, self.errors = [], [], [], []
        self.coverage = {}
        self.consumed_contexts = set()
        self.consumed_providers = set()
        self.previous_request_seq = 0
        self.pid, self.phase, self.identity = None, None, None
        self.stop = threading.Event()
        self.cancelled = threading.Event()
        self.finished = threading.Event()
        self.thread = None
        self.hashes = {}

    def preflight(self):
        for filename in ("provider.ts", "context_observation.mjs", "runtime_observer.py", "verify.py"):
            path = self.assets / filename
            if path.is_symlink() or not path.is_file() or not path.stat().st_size:
                raise ScoringError(f"trusted asset missing or invalid: {filename}")
            for node in [path, *path.parents]:
                if node.is_symlink():
                    raise ScoringError(f"trusted asset has symlink ancestor: {node}")
                info = node.stat()
                if os.geteuid() == 0 and (info.st_uid != 0 or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)):
                    raise ScoringError(f"trusted asset is candidate-writable: {node}")
            self.hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        credentials = {}
        if os.geteuid() == 0:
            account = pwd.getpwnam("agent")
            credentials = {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": []}
        checked = subprocess.run(["node", "--check", str(self.module)], capture_output=True, text=True, timeout=10,
                                 env={"PATH": os.environ["PATH"]}, cwd="/tmp", **credentials)
        if checked.returncode:
            raise ScoringError("trusted observer syntax failed: " + checked.stderr[-2000:])
        self.source = self.module.read_text()
        self.pause_line = next(i for i, line in enumerate(self.source.splitlines()) if "OBSERVATION_PAUSE" in line)
        # Bind each fact kind to the native direct caller and exact call line.
        self.call_sites = {}
        current = None
        for i, line in enumerate(self.source.splitlines()):
            function = re.search(r"function (\w+)\(", line)
            if function:
                current = function[1]
            kind = re.search(r'observeContextFact\(\{ kind: "([^"]+)"', line)
            if kind:
                self.call_sites[kind[1]] = (current, i)
        return dict(self.hashes)

    def attach(self, pid, phase):
        self.pid, self.phase = pid, phase
        self.identity = process_identity(pid)
        if not self.identity:
            raise ScoringError("CLI disappeared before inspector attach")
        self.thread = threading.Thread(target=self._inspect, daemon=True)
        self.thread.start()

    def _accept(self, fact, stack=None):
        if fact.get("schema") != "context-observation.v1":
            raise ScoringError("invalid trusted observation schema")
        with self.condition:
            envelope = {"pid": self.pid, "start_time": self.identity["start_time"], "phase": self.phase,
                        "observation_seq": len(self.facts) + 1, "script_sha256": self.hashes["context_observation.mjs"], "fact": fact}
            if fact["kind"] == "process_exit":
                envelope["stack"] = stack or []
            self.facts.append(envelope)
            self.condition.notify_all()

    def _inspect(self):
        channel = None
        try:
            deadline = time.monotonic() + 10
            endpoint = None
            while time.monotonic() < deadline and not self.stop.is_set():
                endpoint = inspector_endpoint(self.pid)
                if endpoint:
                    break
                time.sleep(.025)
            if not endpoint:
                raise ScoringError("Node inspector endpoint unavailable")
            current = process_identity(self.pid)
            if not current or current["start_time"] != self.identity["start_time"]:
                raise ScoringError("CLI PID identity changed during attach")
            self.endpoint = {"url": endpoint[0], "socket_inode": endpoint[1]}
            channel = InspectorSocket(endpoint[0])
            scripts, trusted = {}, set()

            def notification(event):
                params = event.get("params", {})
                if event.get("method") == "Debugger.scriptParsed":
                    scripts[params["scriptId"]] = params.get("url", "")
                elif event.get("method") == "Debugger.paused":
                    try:
                        frames = params.get("callFrames", [])
                        frame = frames[0] if frames else {}
                        location = frame.get("location", {})
                        script_id = location.get("scriptId")
                        if frame.get("functionName") != "observeContextFact" or scripts.get(script_id) != self.module.as_uri():
                            self.diagnostics.append({"pause": params.get("reason"), "url": scripts.get(script_id)})
                            return
                        if script_id not in trusted:
                            actual = channel.call("Debugger.getScriptSource", {"scriptId": script_id})["scriptSource"]
                            if hashlib.sha256(actual.encode()).hexdigest() != self.hashes["context_observation.mjs"]:
                                raise ScoringError("trusted observer source hash mismatch")
                            trusted.add(script_id)
                        if location.get("lineNumber") != self.pause_line or len(frames) < 2:
                            raise ScoringError("unexpected trusted observation pause location")
                        sampled = channel.call("Debugger.evaluateOnCallFrame", {
                            "callFrameId": frame["callFrameId"], "expression": "payload", "returnByValue": True})
                        payload = sampled.get("result", {}).get("value")
                        if not isinstance(payload, str):
                            raise ScoringError("trusted observation payload is unavailable")
                        fact = json.loads(payload)
                        caller = frames[1]
                        name, line = self.call_sites.get(fact.get("kind"), (None, None))
                        if (caller.get("functionName") != name or caller.get("location", {}).get("scriptId") != script_id
                                or caller["location"].get("lineNumber") != line):
                            raise ScoringError(f"trusted observation caller/kind mismatch: {fact.get('kind')} expected {(name, line)}, got {(caller.get('functionName'), caller.get('location'))}")
                        stack = [{"function": f.get("functionName"), "url": scripts.get(f.get("location", {}).get("scriptId"), "")} for f in frames]
                        self._accept(fact, stack)
                    finally:
                        channel.call("Debugger.resume")

            channel.notifications = notification
            channel.call("Debugger.enable")
            channel.call("Profiler.enable")
            channel.call("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
            channel.call("Runtime.runIfWaitingForDebugger")
            while not self.stop.is_set():
                snapshot = channel.call("Profiler.takePreciseCoverage")
                for script in snapshot.get("result", []):
                    if not script.get("url", "").startswith(self.repo.as_uri() + "/"):
                        continue
                    called = [f["functionName"] for f in script.get("functions", []) if any(r["count"] > 0 for r in f["ranges"])]
                    if called:
                        self.coverage.setdefault(script["url"], set()).update(called)
                try:
                    channel.call("Runtime.evaluate", {"expression": "void 0", "returnByValue": True})
                except ScoringError as exc:
                    if "Cannot find context" in str(exc) or "Execution context was destroyed" in str(exc):
                        self.diagnostics.append("native execution context completed; detach")
                        break
                    raise
                self.stop.wait(.025)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if self.cancelled.is_set() and isinstance(exc, (EOFError, OSError)):
                self.diagnostics.append("after verifier cancellation: " + message)
            elif not self.stop.is_set():
                self.errors.append(message)
        finally:
            if channel:
                channel.close()
            self.finished.set()
            with self.condition:
                self.condition.notify_all()

    def consume_model_request(self, wire, api, timeout=2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                pending = [e for e in self.facts if e["fact"]["kind"] == "provider_request" and e["observation_seq"] not in self.consumed_providers]
                if pending or self.errors or self.finished.is_set() or time.monotonic() >= deadline:
                    break
                self.condition.wait(deadline - time.monotonic())
            if self.errors:
                raise ScoringError("observer failed: " + "; ".join(self.errors))
            if not pending:
                raise NoUnusedProviderObservation(
                    "observation_incompatible: HTTP request has no unused public provider observation")
            provider = pending[0]
            fact, seq = provider["fact"], provider["observation_seq"]
            if fact.get("api") != api or not same_json(fact.get("payload"), wire):
                raise ScoringError("observation_incompatible: public payload differs from actual HTTP JSON")
            contexts = [e for e in self.facts if e["fact"]["kind"] == "context_ready"
                        and e["fact"].get("session_id") == fact.get("session_id")
                        and e["observation_seq"] < seq and e["observation_seq"] not in self.consumed_contexts]
            if not contexts:
                raise ScoringError("observation_incompatible: provider request has no unused public context")
            context = contexts[-1]
            self.consumed_contexts.add(context["observation_seq"])
            self.consumed_providers.add(seq)
            observation = {"request_seq": len(self.requests) + 1, "phase": self.phase, "pid": self.pid,
                           "session_id": fact["session_id"], "wire_payload": copy.deepcopy(wire),
                           "context": copy.deepcopy(context["fact"]),
                           "events_since_previous_request": copy.deepcopy([e for e in self.facts if self.previous_request_seq < e["observation_seq"] <= seq])}
            self.previous_request_seq = seq
            self.requests.append({"request_seq": observation["request_seq"], "provider_seq": seq, "context_seq": context["observation_seq"]})
            return observation

    def snapshot_events(self):
        with self.condition:
            return copy.deepcopy(self.facts)

    def mark_cancelled(self):
        self.cancelled.set()

    def finish(self, expected_completion, verifier_cancelled=False):
        if verifier_cancelled:
            self.cancelled.set()
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.errors.append("observer did not finish collecting")
        for filename, digest in self.hashes.items():
            path = self.assets / filename
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                self.errors.append("trusted asset changed: " + filename)
        facts = self.snapshot_events()
        kinds = [e["fact"]["kind"] for e in facts]
        result = {"phase": self.phase, "identity": self.identity, "endpoint": getattr(self, "endpoint", None),
                  "fixture_ready": "fixture_ready" in kinds, "boot": "boot" in kinds, "expected_completion": expected_completion,
                  "errors": self.errors, "diagnostics": self.diagnostics, "input_sha256": self.hashes,
                  "native_coverage": {url: sorted(functions) for url, functions in self.coverage.items()},
                  "request_bindings": self.requests, "observations": len(facts)}
        # Full actual context stays with runtime artifacts, never in the task tree.
        with gzip.open(self.output_dir / f"observations-{self.phase}.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(facts, stream, ensure_ascii=True)
        (self.output_dir / f"observer-{self.phase}.json").write_text(json.dumps(result, indent=2))
        return result
