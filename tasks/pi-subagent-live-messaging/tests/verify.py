#!/usr/bin/env python3
"""Behavioral verifier: real Pi parent and child CLI processes, scripted text model.

Only model responses and an ordinary slow external tool are controlled. No
candidate communication transport, queue, routing, or agent-loop code is mocked.
"""
from __future__ import annotations

import argparse
import tempfile
import shutil
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid
from binding import load_binding
from scenario import load_scenario
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CASES = ["plain_parallel", "plain_single", "plain_chain", "direct", "use_finding", "broadcast", "ordered",
         "unicode", "completion_boundary", "invalid_recipient", "self_recipient", "malformed", "finished_recipient", "direct_private", "five_workers_private", "isolation", "reuse", "cancellation", "broadcast_partial", "size_below", "size_at", "size_over", "cleanup_repeated", "cancel_queued"]


def text(message):
    content = message.get("content", "")
    return content if isinstance(content, str) else "\n".join(
        part.get("text", "") for part in (content or []) if part.get("type") == "text")


def model_text_views(message):
    """Read plain text or a JSON envelope without assuming the candidate's format.

    Keep alternative views, rather than appending decoded text: the same finding
    must not be counted twice merely because its envelope can be decoded.
    JSON string values are decoded once; message content itself is not rewritten.
    """
    original = text(message)
    views = [original]
    decoder = json.JSONDecoder()

    def strings(value):
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [s for item in value for s in strings(item)]
        if isinstance(value, dict):
            return [s for key, item in value.items() for s in [key, *strings(item)]]
        return [str(value)]

    # A candidate may prefix its JSON with attribution/instructions or a fence.
    # Only decode complete containers; never interpret arbitrary escape sequences.
    for match in re.finditer(r"[\[{]", original):
        try:
            value, end = decoder.raw_decode(original, match.start())
        except ValueError:
            continue
        suffix = original[end:]
        if suffix.strip() not in ["", "```"]:
            continue
        views.append(original[:match.start()] + "\n".join(strings(value)) + suffix)
        break
    return views


def contains_finding(messages, finding):
    return any(finding in view for message in messages for view in model_text_views(message))


class Case:
    def __init__(self, name, binding=None, scenario=None):
        self.name = name
        self.scenario = scenario
        self.resources = []
        self.fault = None
        self.fault_plan = None
        self.binding = binding or load_binding(None)
        self.request_context = threading.local()
        self.condition = threading.Condition()
        self.events, self.requests, self.errors = [], [], []
        self.steps, self.pids = {}, {}
        self.payloads = {g: ["接口使用 cursor；" + uuid.uuid4().hex] for g in ["one", "two", "three", "four"]}
        if name == "unicode":
            self.payloads["one"][0] += '\n并发限制≠串行化🙂 "path\\cache"'
        if name == "use_finding":
            self.payloads = {g: "Use endpoint /api/items-" + uuid.uuid4().hex for g in ["one", "two", "three", "four"]}
            self.payloads = {g: [p] for g, p in self.payloads.items()}
        self.oversize = None
        if name.startswith("size_"):
            limit = self.scenario.message_max_utf8_bytes
            # Unique markers at both ends catch silent prefix/suffix truncation.
            prefix, suffix = "开头" + uuid.uuid4().hex, uuid.uuid4().hex + "🙂结尾"
            size = limit + {"size_below": -1, "size_at": 0, "size_over": 1}[name]
            payload = prefix + "中" * ((size - len((prefix + suffix).encode())) // 3)
            payload += "x" * (size - len((payload + suffix).encode())) + suffix
            assert len(payload.encode()) == size
            if name == "size_over": self.oversize = payload
            else: self.payloads["one"] = [payload]
        self.used = set()
        if name == "ordered":
            self.payloads["one"].append("更正：空 cursor 也有效；" + uuid.uuid4().hex)
        self.replies = {g: "收到并采用；" + uuid.uuid4().hex for g in ["one", "two", "three", "four"]}
        self.roles = ["A", "B", "C"] if name in ["broadcast", "broadcast_partial", "direct_private", "finished_recipient"] else ["A", "B"]
        if name == "five_workers_private":
            self.roles = ["A", "B", "C", "D", "E"]
        if name == "plain_single":
            self.roles = ["A"]
        self.groups = ["one", "two"] if name in ["isolation", "reuse"] else ["one"]
        if name == "cleanup_repeated": self.groups = ["one", "two", "three", "four"]
        self.observed = set()
        self.completed = set()
        self.closed = False
        self.cancel_ready = threading.Event()
        self.proc = None
        self.started = threading.Event()

    @property
    def current_group(self):
        return getattr(self.request_context, "group", "one")

    def event(self, group, role, kind, **fields):
        with self.condition:
            self.events.append({"sequence": len(self.events), "group": group, "role": role, "event": kind, **fields})
            self.condition.notify_all()

    def has(self, group, role, kind):
        return any(e["group"] == group and e["role"] == role and e["event"] == kind for e in self.events)

    def wait(self, predicate, description):
        with self.condition:
            assert self.condition.wait_for(lambda: self.closed or predicate(), 60 if self.name == "broadcast_partial" else 12), "Timed out: " + description
            assert not self.closed, "case closed"

    def work(self, group, role, stage):
        self.event(group, role, "work:" + stage)
        if stage == "ready":
            boundary = "model_stream_held" if self.name == "completion_boundary" else "work:slow_work"
            self.wait(lambda: all(self.has(group, r, boundary) for r in (["B"] if self.name in ["direct_private", "five_workers_private", "finished_recipient"] else self.roles[1:])), "recipients working")
            if self.name == "finished_recipient":
                self.wait(lambda: self.has(group, "C", "session_shutdown"), "C finished before send")
            if self.name == "broadcast_partial":
                self.fault = self.scenario.block_recipient(self, group, "C")
                self.event(group, "C", "delivery_fault_installed", evidence=self.fault[1])
            if self.name == "cancel_queued": self.scenario.observe_team(self, group, "A")
            return self.payloads[group][0]
        if stage == "slow_work":
            if self.name == "cancellation":
                if all(self.has(group, r, "work:slow_work") for r in self.roles):
                    self.cancel_ready.set()
                self.wait(lambda: False, "cancellation")
            if self.name == "cancel_queued" and role == "B":
                self.wait(lambda: False, "cancel with accepted message still queued")
            self.wait(lambda: self.has(group, "A", "all_sends_returned"), "send accepted before tool completion")
            return "External work completed normally."
        if stage == "observer":
            self.wait(lambda: (group, "B") in self.observed, "private recipient received")
            return "Observer work completed."
        if stage == "hold_sender":
            if self.name == "broadcast":
                self.wait(lambda: all((group, r) in self.observed for r in self.roles[1:]), "all broadcast recipients")
            else:
                self.wait(lambda: self.has(group, "B", "reply_send_returned"), "reply accepted")
            return "Sender continues its investigation."
        raise AssertionError("unexpected stage " + stage)

    def tool(self, name, arguments):
        name, arguments = self.binding.encode(name, arguments, self.current_group)
        return {"index": 0, "id": "call_" + uuid.uuid4().hex, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}

    def call(self, name, arguments):
        return {"tool_calls": [self.tool(name, arguments)]}

    def last_result(self, messages):
        results = [m for m in messages if m.get("role") == "tool"]
        assert results, "missing tool result"
        last = results[-1]
        call_id = last.get("tool_call_id")
        name = next((c["function"]["name"] for m in messages for c in m.get("tool_calls", []) if c["id"] == call_id), "")
        operation = next((op for op in ["team_members", "team_send"] if self.binding.tool_name(op) == name), name)
        raw = text(last)
        try: raw = json.loads(raw)
        except ValueError: pass
        return self.binding.decode(operation, raw, self.current_group)

    def events_error(self, messages):
        result = [m for m in messages if m.get("role") == "tool"][-1]
        return any(e["event"] == "tool_error" and e.get("toolCallId") == result["tool_call_id"] for e in self.events)

    def check_input(self, group, role, messages, payloads, sender):
        # The contract permits any model-visible message role. Do not require
        # the Oracle's custom-message-to-user conversion.
        views = [model_text_views(m) for m in messages]
        incoming = [max(options, key=lambda view: sum(view.count(p) for p in payloads)) for options in views]
        flattened = "\n".join(incoming)
        positions = []
        for payload in payloads:
            occurrences = sum(max(view.count(payload) for view in options) for options in views)
            assert occurrences == 1, f"{group}/{role}: finding absent, truncated, or duplicated in model input"
            matching = [m for m in incoming if payload in m]
            assert self.binding.sender_identity(group, sender) in matching[0], f"{group}/{role}: sender identity missing"
            positions.append(flattened.index(payload))
        assert positions == sorted(positions), "sender order changed"
        assert not any(contains_finding(messages, p) for g in self.groups if g != group for p in self.payloads[g]), "message leaked across teams"
        if self.oversize:
            assert not contains_finding(messages, self.oversize[:38]), "rejected oversized message was delivered"
        assert not self.has(group, sender, "session_shutdown"), "sender ended before delivery"
        self.observed.add((group, role))
        self.event(group, role, "peer_message_in_model_input", sender=sender)

    def respond(self, body, pid):
        messages = body["messages"]
        role, group = "ROOT", "one"
        for message in messages:
            if message.get("role") == "user":
                match = re.search(r"\bROLE:([A-Z]+) GROUP:([a-z]+)", text(message))
                if match:
                    role, group = match.groups()
                    break
        self.request_context.group = group
        actor = (group, role)
        assert self.pids.get(actor) == pid, "model request not associated with the observed Pi process"
        n = self.steps.get(actor, 0)
        self.steps[actor] = n + 1
        self.requests.append({"group": group, "role": role, "step": n, "pid": pid, "body": body})
        self.event(group, role, "model_request", step=n)
        names = {t["function"]["name"] for t in body.get("tools", [])}
        if role == "ROOT":
            if self.name == "cleanup_repeated":
                snapshots = [e["resources"] for e in self.events if e["role"] == "ROOT" and e["event"] == "resource_snapshot"]
                assert len(snapshots) >= n + 1, "missing live-parent resource observation"
                if n >= 2:
                    baseline, current = snapshots[1], snapshots[-1]
                    for resource, count in current.items():
                        assert count <= baseline.get(resource, 0), f"communication resources accumulate across dispatches: {resource} {baseline.get(resource, 0)} -> {count}"
            if n == 0 or (self.name == "reuse" and n == 1) or (self.name == "cleanup_repeated" and n < len(self.groups)):
                assert "subagent" in names, "subagent tool failed to load"
                calls = []
                for g in ([self.groups[n]] if self.name in ["reuse", "cleanup_repeated"] else self.groups):
                    tasks = [{"agent": "worker", "id": r, "task": f"ROLE:{r} GROUP:{g} Investigate independently."} for r in self.roles]
                    args = {"tasks": tasks, "communication": not self.name.startswith("plain_")}
                    if self.name == "plain_single":
                        args = {"agent": "worker", "task": tasks[0]["task"]}
                    if self.name == "plain_chain":
                        args = {"chain": [{"agent": "worker", "task": t["task"]} for t in tasks]}
                    calls.append(self.tool("subagent", args))
                for index, call in enumerate(calls):
                    call["index"] = index
                return {"tool_calls": calls}
            assert n == (len(self.groups) if self.name in ["reuse", "cleanup_repeated"] else 1), "parent should not relay peer discoveries"
            self.completed.add(actor)
            return {"content": "Parent finished."}
        if self.name.startswith("plain_"):
            self.completed.add(actor)
            return {"content": "Independent work completed."}
        assert {self.binding.tool_name("team_send"), self.binding.tool_name("team_members")} <= names, f"{group}/{role}: communication tools absent"
        if role not in ["A", "B"] and self.name in ["direct_private", "five_workers_private", "finished_recipient"]:
            if n == 0 and not (role == "C" and self.name == "finished_recipient"):
                return self.call("test_work", {"stage": "observer"})
            assert not any(contains_finding(messages, p) for p in self.payloads[group]), "direct message leaked to a nonrecipient"
            self.completed.add(actor)
            return {"content": "Nonrecipient finished."}
        if role != "A" and n <= 1:
            assert not any(contains_finding(messages, p) for p in self.payloads[group]), "recipient knew private finding before delivery"
        # Discover peers after the actors we need are genuinely running. A live-only
        # roster need not include queued, finished, or unrelated observer workers.
        discovery_roles = self.roles if self.name in ["broadcast", "broadcast_partial"] else ["A", "B"]
        if n == 0:
            self.wait(lambda: all(self.has(group, r, "model_request") for r in discovery_roles), "discovery peers running")
            return self.call("team_members", {})
        if n == 1:
            membership = self.last_result(messages)
            assert membership["self"] == role, "wrong self identity"
            member_ids = [m["id"] for m in membership["members"]]
            assert len(member_ids) == len(set(member_ids)), "duplicate team identity"
            assert set(discovery_roles) <= set(member_ids) <= set(self.roles), "incorrect team membership"
            assert all(m["agent"] == "worker" for m in membership["members"])
            if self.name == "cancellation":
                return self.call("test_work", {"stage": "slow_work"})
            if role != "A" and self.name == "completion_boundary":
                self.event(group, role, "model_stream_held")
                self.wait(lambda: self.has(group, "A", "all_sends_returned"), "send during final model response")
                return {"content": "My original investigation is complete."}
            return self.call("test_work", {"stage": "ready" if role == "A" else "slow_work"})
        count = len(self.payloads[group])
        if role == "A":
            invalid = {"invalid_recipient": "missing", "self_recipient": "A", "finished_recipient": "C"}
            malformed = self.binding.malformed_sends() if self.name == "malformed" else []
            if self.name == "size_over": malformed = [{"to": "B", "message": self.oversize}]
            preparation = self.scenario.preparation_sends(self) if self.name == "broadcast_partial" and hasattr(self.scenario, "preparation_sends") else []
            if preparation and 2 <= n <= 2 + len(preparation):
                if n > 2:
                    result = self.last_result(messages)
                    assert result["accepted"] == ["C"] and not result["failed"], "queue preparation message was not accepted"
                    self.event(group, "A", "preparation_send_accepted", index=n-3)
                if n < 2 + len(preparation):
                    return self.call("team_send", {"to": "C", "message": preparation[n-2]})
                self.event(group, "C", "queue_capacity_reached", count=len(preparation))
            n -= len(preparation)
            offset = len(malformed) or int(self.name in invalid)
            if 2 <= n < 2 + offset:
                if n > 2:
                    assert self.events_error(messages) or self.binding.invalid_rejected(self.last_result(messages)), "malformed arguments were not explicitly rejected"
                return self.call("team_send", malformed[n - 2] if malformed else {"to": invalid[self.name], "message": "must be rejected"})
            if n == 2 + offset and offset:
                if malformed:
                    assert self.events_error(messages) or self.binding.invalid_rejected(self.last_result(messages)), "malformed arguments were not explicitly rejected"
                else:
                    result = self.last_result(messages)
                    assert result["accepted"] == [] and any(f["id"] == invalid[self.name] and f["reason"] for f in result["failed"]), "invalid recipient accepted"
            sending_n = n - offset
            if 2 <= sending_n <= count + 1:
                if sending_n > 2:
                    result = self.last_result(messages)
                    assert result["accepted"] == ["B"] and not result["failed"]
                args = {"message": self.payloads[group][sending_n - 2]}
                args.update({"broadcast": True} if self.name in ["broadcast", "broadcast_partial"] else {"to": "B"})
                return self.call("team_send", args)
            if sending_n == count + 2:
                result = self.last_result(messages)
                targets = self.roles[1:] if self.name == "broadcast" else ["B"]
                if self.name == "broadcast_partial":
                    assert result["accepted"] == ["B"], "partial broadcast must accept the available recipient only"
                    assert len(result["failed"]) == 1 and result["failed"][0]["id"] == "C" and result["failed"][0]["reason"], "partial broadcast failure was hidden or misattributed"
                    self.scenario.restore_fault(self.fault)
                    self.fault = None
                else:
                    assert set(result["accepted"]) == set(targets) and not result["failed"], "send was not accepted for every live target"
                if self.name == "cancel_queued":
                    self.event(group, role, "accepted_before_cancel")
                    self.cancel_ready.set()
                    self.wait(lambda: False, "parent cancellation after acceptance")
                self.event(group, role, "all_sends_returned")
                return self.call("test_work", {"stage": "hold_sender"})
            if sending_n == count + 3:
                if self.name != "broadcast":
                    self.check_input(group, role, messages, [self.replies[group]], "B")
                self.completed.add(actor)
                return {"content": "Sender finished after live exchange."}
        else:
            if n == 2:
                if role == "C" and self.name == "broadcast_partial":
                    assert not contains_finding(messages, self.payloads[group][0]), "failed broadcast recipient received the finding"
                    self.completed.add(actor)
                    return {"content": "Unavailable recipient finished normally."}
                self.check_input(group, role, messages, self.payloads[group], "A")
                if self.name == "broadcast":
                    self.completed.add(actor)
                    return {"content": "Broadcast used."}
                if self.name == "use_finding":
                    paths = [match.group(0) for m in messages for view in model_text_views(m)
                             for match in re.finditer(r"/api/items-[0-9a-f]{32}", view)]
                    assert paths, "no endpoint in actual recipient input"
                    return self.call("test_probe", {"path": paths[-1]})
                return self.call("team_send", {"to": "A", "message": self.replies[group]})
            if self.name == "use_finding" and n == 3:
                assert self.last_result(messages).get("status") == 200, "recipient used wrong endpoint"
                assert (group, role) in self.used, "probe did not execute"
                return self.call("team_send", {"to": "A", "message": self.replies[group]})
            if n == (4 if self.name == "use_finding" else 3):
                result = self.last_result(messages)
                assert result["accepted"] == ["A"] and not result["failed"], "reply was not accepted"
                self.event(group, role, "reply_send_returned")
                # Keep B alive until A has consumed the reply; this is external
                # work synchronization and supplies no message content.
                self.wait(lambda: (group, "A") in self.observed, "reply in A model input")
                self.completed.add(actor)
                return {"content": "Receiver finished after reply."}
        raise AssertionError(f"Unexpected request {group}/{role}/{n}")


def make_handler(case):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                content_type = "text/plain"
                if self.path == "/event":
                    actor = (body["group"], body["role"])
                    case.started.wait(5)
                    pid = body["pid"]
                    assert type(pid) is int and pid > 1, "invalid worker PID"
                    status = Path(f"/proc/{pid}/status").read_text()
                    assert re.search(r"^Uid:\s+60000\s+60000\s+60000\s+60000$", status, re.M), "event PID is not an isolated worker"
                    assert re.search(r"^NoNewPrivs:\s+1$", status, re.M), "worker can acquire privileges"
                    if actor[1] == "ROOT":
                        assert pid == case.proc.pid, "unexpected root Pi PID"
                    assert actor not in case.pids or case.pids[actor] == pid, "actor PID changed"
                    case.pids[actor] = pid
                    case.event(*actor, body["event"], **{k: v for k, v in body.items() if k not in ["group", "role", "event"]})
                    payload = b"ok"
                elif self.path == "/fault-plan":
                    payload = json.dumps(case.fault_plan).encode()
                elif self.path == "/probe":
                    actor = (body["group"], body["role"])
                    expected = re.search(r"/api/items-[0-9a-f]{32}", case.payloads[body["group"]][0])
                    valid = expected is not None and body["path"] == expected.group(0) and actor in case.observed
                    case.event(*actor, "endpoint_probe", path=body["path"], status=200 if valid else 404)
                    if valid: case.used.add(actor)
                    payload = json.dumps({"status": 200 if valid else 404}).encode()
                elif self.path == "/work":
                    payload = case.work(body["group"], body["role"], body["stage"]).encode()
                elif self.path == "/v1/chat/completions":
                    delta = case.respond(body, int(self.headers["X-Pi-Test-Pid"]))
                    chunks = []
                    completion_id = "chatcmpl-" + uuid.uuid4().hex
                    for d, finish in [(dict(role="assistant", **delta), None), ({}, "tool_calls" if "tool_calls" in delta else "stop")]:
                        chunks.append({"id": completion_id, "object": "chat.completion.chunk",
                                       "created": int(time.time()), "model": "scripted",
                                       "choices": [{"index": 0, "delta": d, "finish_reason": finish}]})
                    payload = ("".join("data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
                    content_type = "text/event-stream"
                else:
                    raise AssertionError("Unexpected HTTP endpoint")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                # A receiver whose transport was deliberately broken may exit.
                # Its closed HTTP connection is not a messaging failure. Keep
                # every assertion, healthy-worker error and parent crash visible.
                expected_disconnect = (
                    isinstance(exc, (BrokenPipeError, ConnectionResetError))
                    and self.path == "/work" and body.get("role") == "C"
                    and case.name == "broadcast_partial"
                    and getattr(case.scenario, "endpoint_fault", False)
                    and case.has("one", "ROOT", "endpoint_fault_triggered")
                )
                if expected_disconnect:
                    case.event("one", "C", "faulted_receiver_http_disconnected")
                if not case.closed and not expected_disconnect:
                    case.errors.append(str(exc))
                payload = json.dumps({"error": {"message": str(exc), "type": "invalid_request_error"}}).encode()
                try:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass
    return Handler


def run_case(name, repo, output, binding_path=None, scenario_path=None):
    directory = output / name
    directory.mkdir(parents=True)
    case = Case(name, load_binding(binding_path), load_scenario(scenario_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(case))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Reports stay root-private. Only this disposable tree is writable by Pi.
    scratch = Path(tempfile.mkdtemp(prefix="pi-behavior-", dir="/tmp"))
    case.scratch = scratch
    agent_dir = scratch / "agent"
    (agent_dir / "agents").mkdir(parents=True)
    for part in ["workspace", "home", "tmp"]:
        (scratch / part).mkdir()
    (agent_dir / "agents/worker.md").write_text("---\nname: worker\ndescription: Investigation worker\n---\nPerform the assigned work.\n")
    (agent_dir / "settings.json").write_text(json.dumps({
        "extensions": [str(Path(__file__).with_name("fixture.ts"))],
        "compaction": {"enabled": False}, "retry": {"enabled": False},
    }))
    for path in [scratch, *scratch.rglob("*")]:
        os.chown(path, 60000, 60000)
        path.chmod(0o700 if path.is_dir() else 0o600)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"), "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_TEXT_TEST_URL": f"http://127.0.0.1:{server.server_port}",
        "NODE_OPTIONS": f"--import={repo}/node_modules/tsx/dist/loader.mjs", "TSX_TSCONFIG_PATH": str(repo / "tsconfig.json"),
        "PI_NO_LOCAL_LLM": "1", "AWS_EC2_METADATA_DISABLED": "true",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    command = ["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")), "/usr/local/bin/node", str(repo / "packages/coding-agent/src/cli.ts"), "--mode", "json", "-p", "--no-session",
               "--model", "text-test/scripted", "-e", str(repo / "packages/coding-agent/examples/extensions/subagent/index.ts"),
               "Coordinate the investigation."]
    if name == "broadcast_partial" and getattr(case.scenario, "endpoint_fault", False):
        env["PI_TEXT_ENDPOINT_FAULT"] = "1"
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=scratch / "workspace", env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    case.proc = proc
    case.started.set()
    cancelled = False
    if name in ["cancellation", "cancel_queued"]:
        if case.cancel_ready.wait(25):
            proc.send_signal(signal.SIGTERM)
            cancelled = True
        else:
            case.errors.append("children never reached cancellation boundary")
    try:
        stdout, stderr = proc.communicate(timeout=100 if name == "broadcast_partial" else 45)
    except subprocess.TimeoutExpired:
        case.errors.append("parent timeout")
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    def live_children():
        alive = []
        for actor, pid in case.pids.items():
            if actor[1] == "ROOT":
                continue
            try:
                state = Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[0]
                if state != "Z":
                    alive.append(pid)
            except FileNotFoundError:
                pass
        return alive

    cleanup_started = time.monotonic()
    child_alive = live_children()
    # Cancellation is asynchronous. Observe bounded termination without killing
    # children on the candidate's behalf; persistent orphans still fail below.
    while cancelled and child_alive and time.monotonic() - cleanup_started < 6:
        time.sleep(0.05)
        child_alive = live_children()
    cleanup_wait = time.monotonic() - cleanup_started
    if child_alive:
        case.errors.append(f"child processes still alive: {child_alive}")
        for pid in child_alive:
            try:
                # Never perform a privileged kill on a candidate-reported PID.
                subprocess.run(["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")),
                                "--kill", str(pid)], env={"PATH": "/usr/bin:/bin"}, check=False)
            except ProcessLookupError:
                pass
    with case.condition:
        case.closed = True
        case.condition.notify_all()
    server.shutdown()
    server.server_close()
    expected_actors = {("one", "ROOT")} | {(g, r) for g in case.groups for r in case.roles}
    processes_ok = expected_actors == case.pids.keys() and len(set(case.pids.values())) == len(expected_actors)
    required_actors = expected_actors.copy()
    if name == "broadcast_partial" and getattr(case.scenario, "endpoint_fault", False):
        # A broken transport need not recover: crash recovery is explicitly out of scope.
        # The healthy recipient must still receive the finding and reply; failed C must
        # be named by the real send result, and every process must terminate.
        required_actors.discard(("one", "C"))
        if not case.has("one", "ROOT", "endpoint_fault_triggered"):
            case.errors.append("selected endpoint fault did not execute")
    completion_ok = required_actors <= case.completed
    if name in ["cancellation", "cancel_queued"]:
        completion_ok = cancelled and not child_alive
    if case.fault is not None:
        case.scenario.restore_fault(case.fault)
    if name == "cancel_queued":
        try: case.scenario.assert_cancelled_resources(case)
        except AssertionError as exc: case.errors.append(str(exc))
    leftovers = list((scratch / "tmp").glob("pi-team-*"))
    # Temporary implementation resources are diagnostic only; no grading on
    # a particular storage name or on harmless retained logs.
    passed = processes_ok and completion_ok and not case.errors and (cancelled or proc.returncode == 0)
    result = {"name": name, "passed": passed, "exit_code": proc.returncode, "errors": case.errors,
              "actors": {f"{g}/{r}": pid for (g, r), pid in case.pids.items()},
              "observed": sorted(f"{g}/{r}" for g, r in case.observed),
              "completed": sorted(f"{g}/{r}" for g, r in case.completed),
              "diagnostic_retained_paths": [str(p) for p in leftovers],
              "cleanup_wait_seconds": round(cleanup_wait, 3),
              "elapsed_seconds": round(time.monotonic() - started, 2)}
    (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (directory / "requests.json").write_text(json.dumps(case.requests, ensure_ascii=False, indent=2))
    (directory / "events.json").write_text(json.dumps(case.events, ensure_ascii=False, indent=2))
    (directory / "stdout.jsonl").write_text(stdout)
    (directory / "stderr.txt").write_text(stderr)
    # The tree is candidate-owned; shutil.rmtree uses fd-based symlink protection.
    shutil.rmtree(scratch)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/workspace/pi"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier/text-behavior"))
    parser.add_argument("--binding", type=Path, help="Trusted reviewer-owned interface adapter; default is reference interface")
    parser.add_argument("--scenario", type=Path, help="Trusted transport fault and size-boundary profile")
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.cases:
        try:
            result = run_case(name, args.repo.resolve(), args.output, args.binding, args.scenario)
        except Exception as exc:
            result = {"name": name, "passed": False, "errors": [repr(exc)]}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    summary = {"case_count": len(results), "passed": sum(r["passed"] for r in results),
               "external_model_calls": 0, "results": results}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if len(results) == len(args.cases) and all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
