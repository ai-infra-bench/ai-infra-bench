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
import stat
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from message_reader import read_messages, FormatUnsupported, text, contains_finding
from runtime_observer import RuntimeObserver, preflight_harness
from resource_observer import ResourceObserver

CASES = ["plain_parallel", "plain_single", "plain_chain", "plain_off_omitted", "plain_off_false", "direct", "use_finding", "broadcast", "ordered",
         "unicode", "completion_boundary", "invalid_recipient", "self_recipient", "malformed", "finished_recipient", "direct_private", "five_workers_private", "isolation", "reuse", "cancellation", "broadcast_finished", "size_below", "size_at", "size_over", "cleanup_repeated", "cancel_queued", "queued_steering_direct", "queued_steering_ordered", "broadcast_pressure", "transport_fault"]


def retained_ipc_paths(scratch):
    """Observe IPC nodes in this run's private tree, without interpreting names.

    Ordinary files may be retained logs, so their presence alone is not a leak.
    Do not follow symlinks into other runs or host directories. This observation
    covers filesystem IPC nodes, not every possible transport resource.
    """
    retained = []
    for directory, _, files in os.walk(scratch, followlinks=False):
        for name in files:
            path = Path(directory) / name
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:  # Asynchronous candidate cleanup.
                continue
            if stat.S_ISSOCK(mode) or stat.S_ISFIFO(mode):
                retained.append(str(path))
    return sorted(retained)


def check_send_result(result, accepted, failed=()):
    assert isinstance(result, dict), "send result must be a JSON object"
    a, f = result.get("accepted"), result.get("failed")
    assert isinstance(a, list) and all(isinstance(x, str) for x in a), "invalid accepted IDs"
    assert isinstance(f, list) and all(isinstance(x, dict) and isinstance(x.get("id"), str)
        and isinstance(x.get("reason"), str) and x["reason"] for x in f), "invalid failed recipients"
    ids = a + [x["id"] for x in f]
    assert len(ids) == len(set(ids)), "duplicate or contradictory recipient results"
    assert set(a) == set(accepted) and {x["id"] for x in f} == set(failed), "incorrect recipient outcomes"


def invalid_rejected(result):
    if not isinstance(result, dict) or result.get("accepted") != [] or not result.get("failed"):
        return False
    try:
        failed = result["failed"]
        check_send_result(result, [], [entry["id"] for entry in failed])
        return True
    except (AssertionError, KeyError, TypeError):
        return False


class Case:
    def __init__(self, name):
        self.pressure = name == "broadcast_pressure"
        if self.pressure:
            name = "broadcast"
        self.prefill_calls = {}
        self.accepted_prefill = []
        self.pressure_targets = set()
        self.pressure_settled = set()
        self.pressure_window_started = set()
        self.ordinary_steering = name in ["queued_steering_direct", "queued_steering_ordered"]
        if self.ordinary_steering:
            name = name.removeprefix("queued_steering_")
        self.name = name
        self.request_context = threading.local()
        self.condition = threading.Condition()
        self.events, self.requests, self.errors = [], [], []
        self.steps, self.pids = {}, {}
        self.calls, self.states, self.discovered, self.ledger = {}, {}, {}, {}
        self.infrastructure_errors = []
        self.coverage = {"strict_checks": 0, "fifo_pairs": 0, "handoff_deliveries": 0}
        self.off_markers = ["disabled-private-" + uuid.uuid4().hex, "disabled-broadcast-" + uuid.uuid4().hex]
        self.payloads = {g: ["接口使用 cursor；" + uuid.uuid4().hex] for g in ["one", "two", "three", "four"]}
        if name == "unicode":
            self.payloads["one"][0] += '\n并发限制≠串行化🙂 "path\\cache"'
        if name == "use_finding":
            self.payloads = {g: "Use endpoint /api/items-" + uuid.uuid4().hex for g in ["one", "two", "three", "four"]}
            self.payloads = {g: [p] for g, p in self.payloads.items()}
        self.oversize = None
        if name.startswith("size_"):
            # Unique markers at both ends catch silent prefix/suffix truncation.
            prefix, suffix = "开头" + uuid.uuid4().hex, uuid.uuid4().hex + "🙂结尾"
            size = {"size_below": 65535, "size_at": 65536, "size_over": 65537}[name]
            remaining = size - len((prefix + suffix).encode("utf8"))
            payload = prefix + "界" * (remaining // 3) + "x" * (remaining % 3) + suffix
            self.oversize = payload
        self.used = set()
        if name in ["ordered", "cancel_queued"]:
            self.payloads["one"].append("更正：空 cursor 也有效；" + uuid.uuid4().hex)
        if name == "transport_fault":
            self.payloads["one"] = ["Warmup B " + uuid.uuid4().hex, "Warmup C " + uuid.uuid4().hex, "Broadcast after boundary " + uuid.uuid4().hex]
        self.replies = {g: "收到并采用；" + uuid.uuid4().hex for g in ["one", "two", "three", "four"]}
        self.roles = ["A", "B", "C"] if name in ["broadcast", "broadcast_finished", "direct_private", "finished_recipient", "transport_fault"] else ["A", "B"]
        if name == "five_workers_private":
            self.roles = ["A", "B", "C", "D", "E"]
        if name == "plain_single":
            self.roles = ["A"]
        self.ids = {r: "worker-" + uuid.uuid4().hex for r in self.roles}
        self.plain_results = {r: "Investigation result " + uuid.uuid4().hex for r in self.roles}
        self.groups = ["one", "two"] if name in ["isolation", "reuse"] else ["one"]
        if name == "cleanup_repeated": self.groups = ["one", "two", "three", "four"]
        self.observed = set()
        self.deliveries = {}
        self.model_texts = {}
        self.stale_payloads = []
        self.completed = set()
        self.closed = False
        self.cancel_ready = threading.Event()
        self.proc = None
        self.runtime = None
        self.resources = None
        self.started = threading.Event()
        self.output_handles = []
        self.forced_stop = False
        self.teardown_diagnostics = []

    @property
    def current_group(self):
        return getattr(self.request_context, "group", "one")

    def event(self, group, role, kind, **fields):
        with self.condition:
            self.events.append({"sequence": len(self.events), "monotonic_time": time.monotonic(), "group": group, "role": role, "event": kind, **fields})
            self.condition.notify_all()

    def has(self, group, role, kind):
        return any(e["group"] == group and e["role"] == role and e["event"] == kind for e in self.events)

    def wait(self, predicate, description):
        with self.condition:
            assert self.condition.wait_for(lambda: self.closed or predicate(), 60 if self.name == "transport_fault" else (45 if self.pressure else 12)), "Timed out: " + description
            assert not self.closed, "case closed"

    def work(self, group, role, stage):
        self.event(group, role, "work:" + stage)
        if stage == "ready":
            boundary = "model_stream_held" if self.name == "completion_boundary" else "work:slow_work"
            self.wait(lambda: all(self.has(group, r, boundary) for r in (["B"] if self.name in ["direct_private", "five_workers_private", "finished_recipient", "broadcast_finished"] else self.roles[1:])), "recipients working")
            if self.name in ["finished_recipient", "broadcast_finished"]:
                self.wait(lambda: self.has(group, "C", "session_shutdown"), "C finished before send")
            if self.name in ["direct_private", "five_workers_private"]:
                # Base's parallel dispatcher has four execution slots. In the
                # five-worker case E is queued until an observer completes.
                self.wait(lambda: all(self.has(group, r, "work:observer") for r in self.roles[2:4]), "nonrecipients working before private send")
            if self.name == "isolation":
                # Pi's default tool execution is parallel. Hold both teams at
                # a public external-work boundary before either team sends.
                self.wait(lambda: all(self.has(g, "B", "work:slow_work") for g in self.groups), "both teams running before send")
            return self.payloads[group][0]
        if stage == "slow_work":
            if self.name == "cancellation":
                if all(self.has(group, r, "work:slow_work") for r in self.roles):
                    self.cancel_ready.set()
                self.wait(lambda: False, "cancellation")
            if self.pressure and role == "C" and group not in self.pressure_window_started:
                self.pressure_window_started.add(group)
                self.event(group, role, "pressure_window_open")
                # Hold one finite congestion window. Fast explicit rejections
                # can reach the broadcast while C remains busy; a blocked send
                # still gets an independent release and can drain thereafter.
                with self.condition:
                    self.condition.wait_for(lambda: self.closed or self.has(group, "A", "pressure_send_completed"), 20.0)
                self.event(group, role, "pressure_window_closed")
                self.arm_due(group, role)
            else:
                self.finite_work(group, role)
            return "External work completed normally."
        if stage == "fault_hold":
            self.wait(lambda: self.has(group, "A", "fault_prepared"), "automatic fault observation boundary")
            self.finite_work(group, role)
            return "External work completed normally."
        if stage == "hold_cancel":
            # Warmup already established a real delivery path. Do not assume a
            # queue capacity: a blocked rendezvous is also cancellable.
            with self.condition:
                self.condition.wait_for(lambda: self.closed or any(
                    x["accepted"] is True and x["body"] == self.payloads[group][1]
                    for x in self.ledger.values()), 0.5)
            self.cancel_ready.set()
            self.wait(lambda: False, "cancellation while recipient is working")
        if stage in ["hold_sender", "send_retry", "off_work", "after_delivery"]:
            self.finite_work(group, role)
            return "External work completed normally."
        if stage == "observer":
            self.wait(lambda: (group, "B") in self.observed, "private recipient received")
            return "Observer work completed."
        raise AssertionError("unexpected stage " + stage)

    def tool(self, name, arguments):
        call_id = "call_" + uuid.uuid4().hex
        actor = getattr(self.request_context, "actor", (self.current_group, "ROOT"))
        self.calls[call_id] = {"actor": actor, "name": name, "args": dict(arguments), "result": None}
        if name == "team_send" and isinstance(arguments.get("message"), str) and arguments["message"]:
            targets = list(self.ids.values()) if arguments.get("broadcast") is True and "to" not in arguments else [arguments.get("to")]
            for target in targets:
                if target in self.ids.values() and target != self.ids.get(actor[1]):
                    self.ledger[(call_id, target)] = {"group": actor[0], "sender": self.ids.get(actor[1]),
                        "target": target, "body": arguments["message"], "accepted": None,
                        "first_seen": None, "due": None, "issued": len(self.calls)}
        if self.resources and name == "team_send":
            for (issued_id, target), item in self.ledger.items():
                if issued_id == call_id:
                    self.resources.observe_event({"kind": "message", "sender": item["sender"], "recipient": target, "body": item["body"]})
        return {"index": 0, "id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}

    def call(self, name, arguments):
        return {"tool_calls": [self.tool(name, arguments)]}

    def last_result(self, messages):
        results = [m for m in messages if m.get("role") == "tool"]
        assert results, "missing tool result"
        last = results[-1]
        raw = text(last)
        try: raw = json.loads(raw)
        except ValueError: pass
        if not last.get("isError") and last.get("toolName") == "team_send":
            assert isinstance(raw, dict), "send result must be a JSON object"
            accepted, failed = raw.get("accepted"), raw.get("failed")
            assert isinstance(accepted, list) and all(isinstance(x, str) for x in accepted), "invalid accepted IDs"
            assert isinstance(failed, list) and all(isinstance(x, dict) and isinstance(x.get("id"), str) and isinstance(x.get("reason"), str) and x["reason"] for x in failed), "invalid failed recipients"
            check_send_result(raw, accepted, [x["id"] for x in failed])
        if not last.get("isError") and last.get("toolName") == "team_members":
            assert isinstance(raw, dict) and isinstance(raw.get("self"), str), "invalid team discovery identity"
            members = raw.get("members")
            assert isinstance(members, list) and all(isinstance(m, dict) and isinstance(m.get("id"), str) for m in members), "invalid team member records"
        return raw

    def events_error(self, messages):
        result = [m for m in messages if m.get("role") in ["tool", "toolResult"]][-1]
        return result.get("isError") is True and bool(text(result).strip())

    def check_input(self, group, role, messages, payloads, sender):
        # The contract permits any model-visible message role. Do not require
        # the Oracle's custom-message-to-user conversion.
        self.audit_input(group, role, messages)
        deliveries = self.incoming(group, role, messages)
        reading = read_messages(deliveries, payloads, self.ids.values())
        positions = []
        for payload in payloads:
            assert reading.count(payload) == 1, f"{group}/{role}: finding absent, truncated, or duplicated in model input"
            assert reading.has_sender(payload, self.ids.get(sender, sender)), f"{group}/{role}: sender identity missing or incorrect"
            positions.append(reading.first_position(payload))
        assert positions == sorted(positions), "sender order changed"
        self.deliveries[(group, role)] = list(payloads)
        self.observed.add((group, role))
        self.event(group, role, "peer_message_in_model_input", sender=sender)

    def incoming(self, group, role, messages):
        # Model-authored quotes and ordinary send acknowledgements are not new
        # incoming deliveries. Native Pi observations preserve tool provenance.
        authored = self.model_texts.get((group, role), set())
        return [m for m in messages if not (m.get("role") == "assistant" and text(m) in authored)
                and not (m.get("role") == "tool" and m.get("toolName") in ["team_send", "team_members"])]

    def check_pressure_input(self, group, role):
        deliveries = [self.incoming(group, role, r["body"]["messages"])
                      for r in self.requests if (r["group"], r["role"]) == (group, role)]
        expected = (self.accepted_prefill if role == "C" else []) + (self.payloads[group] if role in self.pressure_targets else [])
        forbidden = [p for p in self.prefill_calls.values() if role != "C" or p not in self.accepted_prefill]
        if role not in self.pressure_targets: forbidden += self.payloads[group]
        readings = [read_messages(messages, [*expected, *forbidden], self.ids.values()) for messages in deliveries]
        for payload in expected:
            seen = False
            for reading in readings:
                assert reading.count(payload) <= 1, "finding duplicated in pressure model input"
                if reading.count(payload):
                    assert reading.has_sender(payload, self.ids["A"]), "sender identity missing or incorrect"
                    seen = True
            assert seen, f"{group}/{role}: accepted finding absent or truncated under pressure"
        assert not any(reading.count(p) for reading in readings for p in forbidden), "rejected or private prefill was delivered"
        self.deliveries[(group, role)] = expected
        self.observed.add((group, role))
        self.event(group, role, "peer_message_in_model_input", sender="A")

    def audit_input(self, group, role, messages):
        incoming = self.incoming(group, role, messages)
        if self.oversize and any(item["body"] == self.oversize and item["accepted"] is False for item in self.ledger.values()):
            assert not contains_finding(incoming, self.oversize[:38]), "rejected oversized message was delivered"
        assert not any(contains_finding(incoming, p) for p in self.stale_payloads), "old message leaked after cancellation"
        assert not any(contains_finding(incoming, p) for g in self.payloads if g != group
                       for p in [*self.payloads[g], self.replies[g]]), "message leaked across teams"
        rejected = []
        if self.name in ["invalid_recipient", "self_recipient", "finished_recipient"]:
            rejected = ["must be rejected"]
        if self.name == "malformed":
            rejected = ["no recipient", "ambiguous", "unexpected"]
        assert not any(contains_finding(incoming, p) for p in rejected), "rejected request was delivered"
        for payload in self.deliveries.get((group, role), []):
            count = read_messages(incoming, [payload], self.ids.values()).count(payload)
            assert count <= 1, f"{group}/{role}: finding duplicated in a later model input"
        if role == "A" and self.name in ["broadcast", "broadcast_finished", "transport_fault"]:
            peer_input = [m for m in incoming if not (m.get("role") == "tool" and m.get("toolName") == "test_work")]
            assert not any(contains_finding(peer_input, p) for p in self.payloads[group]), "broadcast delivered to sender"

    def exclude_observer_ports(self):
        if self.resources and self.runtime:
            for record in list(self.runtime.inspections.values()):
                if record.get("port"):
                    self.resources.observe_event({"kind": "exclude_port", "port": record["port"]})

    def finite_work(self, group, role):
        # This timer never depends on peer progress; rendezvous/backpressure can drain.
        with self.condition:
            self.condition.wait_for(lambda: self.closed, 0.15)
            assert not self.closed, "case closed"
            self.arm_due(group, role)

    def arm_due(self, group, role):
        with self.condition:
            next_call = self.steps.get((group, role), 0)
            for item in self.ledger.values():
                if item["group"] == group and item["target"] == self.ids.get(role) and item["accepted"] is True and item["first_seen"] is None:
                    item["due"] = next_call if item["due"] is None else min(next_call, item["due"])

    def record_result(self, group, role, call_id, name, result, is_error=False):
        with self.condition:
            call = self.calls.get(call_id)
            assert call is not None, "result for an unissued tool call"
            assert call["actor"] == (group, role) and call["name"] == name, "tool result belongs to another call or worker"
            message = {"role": "tool", "tool_call_id": call_id, "toolName": name,
                       "content": result.get("content", []), "isError": bool(is_error)}
            if call["result"] is not None:
                assert call["result"] == message, "contradictory result for a completed call"
                return
            call["result"] = message
            if name == "team_send":
                raw = self.last_result([message])
                if not is_error:
                    assert isinstance(raw, dict), "send result must be a JSON object"
                if not is_error and isinstance(raw, dict):
                    accepted = raw.get("accepted", [])
                    failed = raw.get("failed", [])
                    assert isinstance(accepted, list) and all(isinstance(x, str) for x in accepted), "invalid accepted IDs"
                    assert isinstance(failed, list) and all(isinstance(x, dict) and isinstance(x.get("id"), str) and isinstance(x.get("reason"), str) and x["reason"] for x in failed), "invalid failed recipients"
                    check_send_result(raw, accepted, [x["id"] for x in failed])
                    if self.pressure and call["args"].get("broadcast"):
                        self.coverage["pressure_broadcast_during_hold"] = self.has(group, "C", "pressure_window_open") and not self.has(group, "C", "pressure_window_closed")
                        self.coverage["partial_broadcast_outcome"] = bool(accepted and failed)
                        self.event(group, role, "pressure_send_completed")
                    for key, item in self.ledger.items():
                        if key[0] == call_id:
                            item["accepted"] = item["target"] in accepted
                            if item["accepted"] and item["body"] == self.oversize:
                                self.accepted_large = self.oversize
                                self.oversize = None
                else:
                    for key, item in self.ledger.items():
                        if key[0] == call_id:
                            item["accepted"] = False
            self.event(group, role, "native_tool_result", call_id=call_id, tool=name)

    def result_for(self, call_id, messages):
        call = self.calls[call_id]
        matches = [m for m in messages if m.get("role") == "tool" and m.get("tool_call_id") == call_id]
        assert len(matches) == 1, "missing or duplicate result for expected tool call"
        message = matches[0]
        assert message.get("toolName") == call["name"], "tool result name changed"
        assert call["result"] is not None, "native tool completion was not observed"
        assert text(message) == text(call["result"]) and bool(message.get("isError")) == call["result"]["isError"], "tool result changed after completion"
        return message

    def send_to(self, group, role, recipient):
        address = self.ids[recipient]
        assert address in self.discovered[(group, role)], "running recipient absent from discovery"
        return next(value for value in self.discovered[(group, role)] if value == address)

    def issue(self, actor, name, args, purpose):
        response = self.call(name, args)
        self.states[actor]["pending"] = response["tool_calls"][0]["id"]
        self.states[actor]["purpose"] = purpose
        return response

    def consume_pending(self, actor, messages):
        state = self.states[actor]
        call_id = state.pop("pending", None)
        if call_id is None:
            return None, None, None
        message = self.result_for(call_id, messages)
        purpose = state.pop("purpose")
        return purpose, message, self.last_result([message])

    def observe_ledger(self, group, role, messages, n):
        deliveries = self.incoming(group, role, messages)
        items = [item for item in self.ledger.values() if item["group"] == group and item["target"] == self.ids.get(role)]
        reading = read_messages(deliveries, [item["body"] for item in items], self.ids.values())
        for item in items:
            payload = item["body"]
            count = reading.count(payload)
            assert count <= 1, "finding duplicated in model input"
            if count:
                assert item["accepted"] is not False, "rejected message was delivered"
                assert reading.has_sender(payload, item["sender"]), "sender identity missing or incorrect"
                if item["first_seen"] is None:
                    item["first_seen"] = (n, reading.first_position(payload))
                    self.coverage["handoff_deliveries"] += int(item["due"] is None)
                    if self.resources:
                        self.resources.observe_event({"kind": "delivery", "recipient": item["target"], "body": payload})
            if item["due"] is not None and item["due"] <= n:
                self.coverage["strict_checks"] += 1
                assert item["first_seen"] is not None, "accepted message absent from its required next model call"
                item["due"] = None
        # Only non-overlapping normal sends have a declared order. Concurrent prefill does not.
        ordered = [item for item in items if item["sender"] == self.ids["A"] and item["body"] in self.payloads[group] and item["accepted"] is True and item["first_seen"] is not None]
        ordered.sort(key=lambda item: item["issued"])
        if len(ordered) >= 2:
            assert [x["first_seen"] for x in ordered] == sorted(x["first_seen"] for x in ordered), "sender order changed"
            self.coverage["fifo_pairs"] = max(self.coverage["fifo_pairs"], len(ordered) - 1)

    def plan_sender(self, group):
        plan = []
        if self.name == "transport_fault":
            return [("warmup", {"to": self.send_to(group, "A", role), "message": self.payloads[group][index]}) for index, role in enumerate(["B", "C"])] + [("fault_broadcast", {"broadcast": True, "message": self.payloads[group][2]})]
        if self.name in ["invalid_recipient", "self_recipient", "finished_recipient"]:
            target = {"invalid_recipient": "missing-" + uuid.uuid4().hex, "self_recipient": self.ids["A"], "finished_recipient": self.ids.get("C")}[self.name]
            plan.append(("invalid" if self.name != "finished_recipient" else "finished", {"to": target, "message": "must be rejected"}))
        if self.name == "malformed":
            plan.extend(("invalid", args) for args in [{"message": "no recipient"}, {"to": self.ids["B"], "broadcast": True, "message": "ambiguous"}, {"to": self.ids["B"], "message": {"unexpected": True}}, {"to": self.ids["B"], "message": ""}])
        if self.oversize:
            plan.append(("size", {"to": self.ids["B"], "message": self.oversize}))
        for payload in self.payloads[group]:
            args = {"message": payload}
            args.update({"broadcast": True} if self.name in ["broadcast", "broadcast_finished"] else {"to": self.send_to(group, "A", "B")})
            plan.append(("main", args))
        return plan

    def respond(self, body, pid):
        messages = body["messages"]
        role, group = "ROOT", "one"
        for message in messages:
            if message.get("role") == "user":
                match = re.search(r"\bROLE:([A-Z]+) GROUP:([a-z]+)", text(message))
                if match:
                    role, group = match.groups()
                    break
        actor = (group, role)
        self.request_context.group, self.request_context.actor = group, actor
        assert self.pids.get(actor) == pid, "model request not associated with the observed Pi process"
        n = self.steps.get(actor, 0)
        self.steps[actor] = n + 1
        self.requests.append({"group": group, "role": role, "step": n, "pid": pid, "body": body})
        self.event(group, role, "model_request", step=n)
        names = {t["function"]["name"] for t in body.get("tools", [])}
        if role == "ROOT":
            if n and self.name.startswith("plain_"):
                results = [m for m in messages if m.get("role") == "tool"]
                assert results and not any(m.get("isError") for m in results), "ordinary subagent call failed"
                expected = self.roles[-1:] if self.name == "plain_chain" else self.roles
                assert all(contains_finding(results, self.plain_results[r]) for r in expected), "child result missing from parent output"
            if n == 0 or (self.name == "reuse" and n == 1) or (self.name == "cleanup_repeated" and n < len(self.groups)):
                assert "subagent" in names, "subagent tool failed to load"
                calls = []
                for g in ([self.groups[n]] if self.name in ["reuse", "cleanup_repeated"] else self.groups):
                    tasks = [{"agent": "worker", "id": self.ids[r], "task": f"ROLE:{r} GROUP:{g} Investigate independently."} for r in self.roles]
                    args = {"tasks": tasks, "communication": not self.name.startswith("plain_")}
                    if self.name == "plain_parallel":
                        args = {"tasks": [{k: v for k, v in task.items() if k != "id"} for task in tasks]}
                    elif self.name == "plain_off_omitted": args = {"tasks": tasks}
                    elif self.name == "plain_single": args = {"agent": "worker", "task": tasks[0]["task"]}
                    elif self.name == "plain_chain": args = {"chain": [{"agent": "worker", "task": t["task"]} for t in tasks]}
                    calls.append(self.tool("subagent", args))
                for index, call in enumerate(calls): call["index"] = index
                return {"tool_calls": calls}
            assert n == (len(self.groups) if self.name in ["reuse", "cleanup_repeated"] else 1), "parent should not relay peer discoveries"
            self.completed.add(actor)
            return {"content": "Parent finished."}
        self.audit_input(group, role, messages)
        self.observe_ledger(group, role, messages, n)
        if actor in self.completed:
            assert self.ordinary_steering and n <= 12, "unexpected model call after completion"
            return {"content": "Processed pending input; investigation complete."}
        state = self.states.setdefault(actor, {"phase": "discover"})
        if self.name in ["plain_parallel", "plain_off_omitted", "plain_off_false"]:
            return self.respond_off(actor, messages, names)
        if self.name.startswith("plain_"):
            self.completed.add(actor)
            return {"content": self.plain_results[role]}
        assert {"team_send", "team_members"} <= names, f"{group}/{role}: communication tools absent"
        if role not in ["A", "B"] and self.name in ["direct_private", "five_workers_private", "finished_recipient", "broadcast_finished"]:
            if n == 0 and not (role == "C" and self.name in ["finished_recipient", "broadcast_finished"]):
                return self.call("test_work", {"stage": "observer"})
            assert not any(contains_finding(messages, p) for p in self.payloads[group]), "direct message leaked to a nonrecipient"
            self.completed.add(actor)
            return {"content": "Nonrecipient finished."}
        if state["phase"] == "discover":
            discovery_roles = self.roles if self.name in ["broadcast", "transport_fault"] else ["A", "B"]
            self.wait(lambda: all(self.has(group, r, "model_request") for r in discovery_roles), "discovery peers running")
            state["phase"] = "discovery_result"
            return self.issue(actor, "team_members", {}, "discovery")
        if state["phase"] == "discovery_result":
            _, message, membership = self.consume_pending(actor, messages)
            assert not message.get("isError") and isinstance(membership, dict), "team discovery failed"
            assert membership.get("self") == self.ids[role], "wrong self identity"
            members = membership.get("members")
            assert isinstance(members, list) and all(isinstance(m, dict) and isinstance(m.get("id"), str) for m in members), "invalid team member records"
            member_ids = [m["id"] for m in members]
            assert all(isinstance(x, str) for x in member_ids) and len(member_ids) == len(set(member_ids)), "duplicate or invalid team identity"
            expected = self.roles if self.name in ["broadcast", "transport_fault"] else ["A", "B"]
            assert {self.ids[r] for r in expected if r != role} <= set(member_ids) <= set(self.ids.values()), "incorrect team membership"
            self.discovered[actor] = member_ids
            state["phase"] = "sender" if role == "A" else "receiver"
            if self.name == "cancellation": return self.issue(actor, "test_work", {"stage": "slow_work"}, "work")
            if role != "A" and self.name == "completion_boundary":
                self.event(group, role, "model_stream_held")
                with self.condition: self.condition.wait_for(lambda: self.closed, 0.4)
                state["terminal_attempt"] = True
                # Accepted messages must cause Pi to continue after this final response.
                return {"content": "My original investigation is complete."}
            return self.issue(actor, "test_work", {"stage": "ready" if role == "A" else "slow_work"}, "work")
        if role == "A": return self.respond_sender(actor, messages)
        return self.respond_receiver(actor, messages)

    def respond_off(self, actor, messages, names):
        group, role = actor
        state = self.states[actor]
        assert not any(contains_finding(self.incoming(group, role, messages), marker) for marker in self.off_markers), "communication delivered while disabled"
        purpose, message, result = self.consume_pending(actor, messages)
        if purpose == "off_send":
            assert self.events_error([message]) or invalid_rejected(result), "communication accepted or did not explicitly reject while disabled"
        if role == "A":
            if state["phase"] == "discover":
                self.wait(lambda: self.has(group, "B", "work:off_work"), "disabled recipient running")
                state["phase"] = "send"; state["index"] = 0
            index = state["index"]
            if "team_send" in names and index < 2:
                state["index"] += 1
                args = {"message": self.off_markers[index]}
                args.update({"to": self.ids["B"]} if index == 0 else {"broadcast": True})
                return self.issue(actor, "team_send", args, "off_send")
            self.event(group, role, "off_complete")
        elif not self.has(group, "A", "off_complete") or not state.get("followup"):
            state["followup"] = self.has(group, "A", "off_complete")
            return self.issue(actor, "test_work", {"stage": "off_work"}, "work")
        self.completed.add(actor)
        return {"content": self.plain_results[role]}

    def respond_sender(self, actor, messages):
        group, role = actor
        state = self.states[actor]
        purpose, message, result = self.consume_pending(actor, messages)
        if purpose == "warmup":
            check_send_result(result, [state["last_args"]["to"]])
        elif purpose == "fault_broadcast":
            accepted = result.get("accepted", []) if isinstance(result, dict) else []
            expected = [self.ids["B"], self.ids["C"]]
            assert self.ids["B"] in accepted and set(accepted) <= set(expected), "target failure prevented healthy peer acceptance"
            if not state["fault"].get("applied"):
                assert set(accepted) == set(expected), "normal broadcast failed without an injected fault"
            check_send_result(result, accepted, [x for x in expected if x not in accepted])
            self.resources.restore_faults()
        elif purpose in ["invalid", "finished"]:
            args = state["last_args"]
            if purpose == "invalid" and self.events_error([message]): pass
            elif "to" in args and isinstance(args["to"], str) and args.get("broadcast") is not True:
                check_send_result(result, [], [args["to"]])
            else: assert invalid_rejected(result), "malformed arguments were not explicitly rejected"
        elif purpose == "size":
            if self.events_error([message]) or invalid_rejected(result): pass
            else:
                check_send_result(result, [self.ids["B"]])
                self.accepted_large = self.oversize; self.oversize = None
        elif purpose == "main":
            args = state["last_args"]
            assert not message.get("isError"), "ordinary send returned a tool error"
            assert isinstance(result, dict), "send result must be a JSON object"
            expected = [self.ids[r] for r in (self.roles[1:] if self.name == "broadcast" else ["B"])]
            failed_finished = [self.ids["C"]] if self.name == "broadcast_finished" and result.get("failed") else []
            if self.pressure:
                accepted = result.get("accepted", []) if isinstance(result, dict) else []
                assert set(accepted) <= set(expected), "send accepted an unattempted recipient"
                check_send_result(result, accepted, [target for target in expected if target not in accepted])
                self.pressure_targets = {r for r in self.roles if self.ids[r] in accepted}
                self.event(group, role, "pressure_broadcast_result", accepted=list(self.pressure_targets), failed=[r for r in self.roles[1:] if r not in self.pressure_targets])
            elif self.name == "completion_boundary" and result.get("accepted") == []:
                check_send_result(result, [], [self.ids["B"]])
                state["completion_rejected"] = True
            elif self.name == "ordered" and result.get("accepted") == []:
                check_send_result(result, [], [self.ids["B"]])
                if state.get("retries", 0) < 2:
                    # Retry after prior accepted work has actually drained. This
                    # is a continued live send, not a minimum-capacity assertion.
                    self.wait(lambda: all(x["first_seen"] is not None for x in self.ledger.values()
                                          if x["group"] == group and x["sender"] == self.ids["A"] and x["accepted"] is True), "prior accepted messages consumed before retry")
                    state["retries"] = state.get("retries", 0) + 1
                    retry = dict(args, **{"message": "Retry finding " + uuid.uuid4().hex})
                    self.payloads[group].append(retry["message"])
                    state["plan"].insert(0, ("main", retry))
                    return self.issue(actor, "test_work", {"stage": "send_retry"}, "work")
            else: check_send_result(result, expected, failed_finished)
        if "plan" not in state:
            state["plan"] = self.plan_sender(group)
            if self.pressure:
                calls = []
                for index in range(66):
                    prefix = "Queued finding " + uuid.uuid4().hex + "\n"
                    payload = prefix + "x" * (65536 - len(prefix.encode("utf8")))
                    call = self.tool("team_send", {"to": self.send_to(group, "A", "C"), "message": payload})
                    call["index"] = index; self.prefill_calls[call["id"]] = payload; calls.append(call)
                state["prefill_pending"] = True
                return {"tool_calls": calls}
        if state.pop("prefill_pending", False):
            for call_id, payload in self.prefill_calls.items():
                entry = self.result_for(call_id, messages)
                if self.events_error([entry]): continue
                outcome = self.last_result([entry]); accepted = [self.ids["C"]] if outcome.get("accepted") else []
                check_send_result(outcome, accepted, [] if accepted else [self.ids["C"]])
                if accepted: self.accepted_prefill.append(payload)
            self.coverage["prefill_rejections"] = len(self.prefill_calls) - len(self.accepted_prefill)
            self.event(group, role, "prefill_completed", accepted=len(self.accepted_prefill), attempted=len(self.prefill_calls))
        if state["plan"]:
            purpose, args = state["plan"].pop(0); state["last_args"] = args
            if purpose == "fault_broadcast":
                self.wait(lambda: all(self.has(group, recipient, "work:fault_hold") for recipient in ["B", "C"]), "both warmup deliveries observed")
                self.exclude_observer_ports()
                self.resources.snapshot("before_fault")
                state["fault"] = self.resources.fault_target(self.ids["C"])
                self.event(group, role, "fault_prepared", **state["fault"])
            if self.name == "cancel_queued" and args.get("message") == self.payloads[group][1]:
                self.wait(lambda: self.has(group, "B", "work:hold_cancel"), "warmup consumed before queued cancellation")
            return self.issue(actor, "team_send", args, purpose)
        if not self.has(group, role, "all_sends_returned"):
            if self.name == "cancel_queued":
                self.event(group, role, "accepted_before_cancel"); self.cancel_ready.set()
                self.wait(lambda: False, "parent cancellation after acceptance")
            self.event(group, role, "all_sends_returned")
        if state.get("completion_rejected"):
            self.completed.add(actor); self.completed.add((group, "B"))
            return {"content": "Recipient completed before acceptance; send rejected."}
        if self.name in ["broadcast", "transport_fault"]:
            done = all((group, r) in self.observed for r in self.roles[1:])
        else:
            reply = [x for x in self.ledger.values() if x["group"] == group and x["body"] == self.replies[group] and x["target"] == self.ids["A"]]
            done = bool(reply) and all(x["accepted"] is True and x["first_seen"] is not None for x in reply)
        if done:
            self.observed.add(actor); self.completed.add(actor)
            return {"content": "Sender finished after live exchange."}
        return self.issue(actor, "test_work", {"stage": "hold_sender"}, "work")

    def respond_receiver(self, actor, messages):
        group, role = actor
        state = self.states[actor]
        purpose, message, result = self.consume_pending(actor, messages)
        if purpose == "work":
            assert not message.get("isError") and text(message) == "External work completed normally.", "recipient tool did not finish normally"
        if purpose == "probe":
            assert isinstance(result, dict) and result.get("status") == 200 and actor in self.used, "recipient used wrong endpoint"
            state["probed"] = True
        if purpose == "reply":
            check_send_result(result, [self.ids["A"]]); state["replied"] = True
            self.event(group, role, "reply_send_returned")
        items = [x for x in self.ledger.values() if x["group"] == group and x["target"] == self.ids[role] and x["sender"] == self.ids["A"]]
        if self.name == "transport_fault" and not state.get("fault_held") and any(x["first_seen"] is not None for x in items):
            state["fault_held"] = True
            return self.issue(actor, "test_work", {"stage": "fault_hold"}, "work")
        if self.name == "cancel_queued" and any(x["body"] == self.payloads[group][0] and x["first_seen"] is not None for x in items):
            return self.issue(actor, "test_work", {"stage": "hold_cancel"}, "work")
        ready = self.has(group, "A", "all_sends_returned") and all(x["accepted"] is not None and (not x["accepted"] or x["first_seen"] is not None) for x in items)
        if not ready:
            return self.issue(actor, "test_work", {"stage": "slow_work"}, "work")
        accepted = [x for x in items if x["accepted"]]
        if not self.pressure:
            assert accepted, "ordinary communication did not deliver a finding"
        self.observed.add(actor)
        if not state.get("followup"):
            state["followup"] = True
            return self.issue(actor, "test_work", {"stage": "after_delivery"}, "work")
        if self.name in ["broadcast", "transport_fault"]:
            self.completed.add(actor); return {"content": "Broadcast used."}
        if self.name == "use_finding" and not state.get("probed"):
            reading = read_messages(self.incoming(group, role, messages), self.payloads[group], self.ids.values())
            paths = [match.group(0) for payload in self.payloads[group] if reading.occurrences(payload) for match in re.finditer(r"/api/items-[0-9a-f]{32}", payload)]
            assert paths, "no endpoint in actual recipient input"
            return self.issue(actor, "test_probe", {"path": paths[-1]}, "probe")
        if not state.get("replied"):
            return self.issue(actor, "team_send", {"to": self.send_to(group, role, "A"), "message": self.replies[group]}, "reply")
        if (group, "A") not in self.observed:
            return self.issue(actor, "test_work", {"stage": "after_delivery"}, "work")
        self.completed.add(actor)
        return {"content": "Receiver finished after reply."}




def native_observation(context):
    """Read native Context into the existing assertions' shape, without injection.

    Preserve native input separately in requests.json for auditing this bridge.
    No changes are made to the actual Context consumed by Pi's Faux provider.
    """
    messages = []
    for message in context["messages"]:
        item = dict(message)
        if item["role"] == "toolResult":
            item["role"] = "tool"
            item["tool_call_id"] = item["toolCallId"]
        messages.append(item)
    return {"messages": messages,
            "tools": [{"function": {"name": tool["name"]}} for tool in context.get("tools", [])],
            "native_context": context}


def make_handler(case):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            responding = False
            try:
                raw_body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                body = json.loads(raw_body)
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
                        assert case.runtime is not None and case.runtime.owns_process(pid), "unexpected root Pi PID"
                    assert actor not in case.pids or case.pids[actor] == pid, "actor PID changed"
                    case.pids[actor] = pid
                    if case.resources and actor[1] != "ROOT":
                        case.resources.observe_event({"kind": "actor", "pid": pid, "task_id": case.ids[actor[1]]})
                    case.event(*actor, body["event"], **{k: v for k, v in body.items() if k not in ["group", "role", "event"]})
                    if body["event"] == "tool_execution_end":
                        case.record_result(*actor, body["toolCallId"], body["toolName"], body["result"], body["isError"])
                    payload = b"ok"
                elif self.path == "/probe":
                    actor = (body["group"], body["role"])
                    expected = re.search(r"/api/items-[0-9a-f]{32}", case.payloads[body["group"]][0])
                    valid = expected is not None and body["path"] == expected.group(0) and actor in case.observed
                    case.event(*actor, "endpoint_probe", path=body["path"], status=200 if valid else 404)
                    if valid: case.used.add(actor)
                    payload = json.dumps({"status": 200 if valid else 404}).encode()
                elif self.path == "/work":
                    payload = case.work(body["group"], body["role"], body["stage"]).encode()
                elif self.path == "/faux":
                    pid = int(self.headers["X-Pi-Test-Pid"])
                    case.runtime.consume_provider_request(pid, raw_body)
                    delta = case.respond(native_observation(body), pid)
                    case.arm_due(*case.request_context.actor)
                    if "content" in delta:
                        case.model_texts.setdefault(case.request_context.actor, set()).add(delta["content"])
                    payload = json.dumps(delta, ensure_ascii=False).encode()
                    content_type = "application/json"
                else:
                    raise AssertionError("Unexpected HTTP endpoint")
                responding = True
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                if not case.closed:
                    if responding and case.forced_stop and isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                        case.teardown_diagnostics.append(repr(exc))
                    elif not isinstance(exc, AssertionError):
                        case.infrastructure_errors.append(str(exc))
                    else:
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


def _run_case(name, repo, output, case, scratch=None, cleanup_observer=None):
    preflight_harness(Path(__file__).parent)
    directory = output / name
    directory.mkdir(parents=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(case))
    case.server = server
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # Reports stay root-private. Only this disposable tree is writable by Pi.
    if scratch is None:
        scratch = Path(tempfile.mkdtemp(prefix="pi-behavior-", dir="/tmp"))
        agent_dir = scratch / "agent"
        (agent_dir / "agents").mkdir(parents=True, exist_ok=True)
        for part in ["workspace", "home", "tmp"]:
            (scratch / part).mkdir(exist_ok=True)
        (agent_dir / "agents/worker.md").write_text("---\nname: worker\ndescription: Investigation worker\n---\nPerform the assigned work.\n")
        (agent_dir / "settings.json").write_text(json.dumps({
            "extensions": [str(Path(__file__).with_name("fixture.ts"))],
            "compaction": {"enabled": False}, "retry": {"enabled": False},
            **({"steeringMode": "one-at-a-time"} if case.ordinary_steering else {}),
        }))
        for path in [scratch, *scratch.rglob("*")]:
            os.chown(path, 60000, 60000)
            path.chmod(0o700 if path.is_dir() else 0o600)
    case.scratch = scratch
    agent_dir = scratch / "agent"
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC", "HOME": str(scratch / "home"),
        "TMPDIR": str(scratch / "tmp"), "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_TEXT_TEST_URL": f"http://127.0.0.1:{server.server_port}",
        "NODE_OPTIONS": f"--import={repo}/node_modules/tsx/dist/loader.mjs --inspect-brk=127.0.0.1:0", "TSX_TSCONFIG_PATH": str(repo / "tsconfig.json"),
        "PI_NO_LOCAL_LLM": "1", "AWS_EC2_METADATA_DISABLED": "true",
        "PI_TEST_ORDINARY_STEERING": "1" if case.ordinary_steering else "0",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    command = ["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")), "/usr/local/bin/node", str(repo / "packages/coding-agent/src/cli.ts"), "--mode", "json", "-p", "--no-session",
               "--model", "text-test/scripted", "-e", str(repo / "packages/coding-agent/examples/extensions/subagent/index.ts"),
               "Coordinate the investigation."]
    started = time.monotonic()
    if name in ["cancellation", "cancel_queued", "transport_fault"]:
        case.resources = ResourceObserver(repo, directory, server.server_port)
        command = case.resources.wrap_command(command)
    stdout_handle = (directory / "stdout.jsonl").open("w")
    stderr_handle = (directory / "stderr.txt").open("w")
    case.output_handles = [stdout_handle, stderr_handle]
    proc = subprocess.Popen(command, cwd=scratch / "workspace", env=env, stdout=stdout_handle,
                            stderr=stderr_handle, text=True, start_new_session=True)
    case.proc = proc
    case.runtime = RuntimeObserver(proc.pid, directory, repo, server.server_port)
    case.runtime.start()
    case.started.set()
    watching_done = threading.Event()
    def stop_after_assertion():
        while not watching_done.wait(0.1):
            if case.errors and proc.poll() is None:
                parent_pid = case.pids.get(("one", "ROOT"))
                if parent_pid is not None and case.runtime.owns_process(parent_pid):
                    case.forced_stop = True
                    case.event("one", "ROOT", "verifier_stopped_after_failure", reason=case.errors[0])
                    case.runtime.mark_forced_stop()
                    subprocess.run(["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")),
                                    "/usr/bin/kill", "-TERM", str(parent_pid)], check=False, env={"PATH": "/usr/bin:/bin"})
                    return
    threading.Thread(target=stop_after_assertion, daemon=True).start()
    cancelled = False
    if name in ["cancellation", "cancel_queued"]:
        if case.cancel_ready.wait(120):
            # A tracing wrapper is not the Pi parent. Signal the observed Pi
            # process after dropping privilege, never a privileged reported PID.
            parent_pid = case.pids.get(("one", "ROOT"))
            assert parent_pid is not None and case.runtime.owns_process(parent_pid), "parent Pi identity unavailable at cancellation"
            case.forced_stop = True
            case.runtime.mark_forced_stop()
            subprocess.run(["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")),
                            "/usr/bin/kill", "-TERM", str(parent_pid)], check=True, env={"PATH": "/usr/bin:/bin"})
            cancelled = True
        else:
            case.errors.append("children never reached cancellation boundary")
    try:
        stdout, stderr = proc.communicate(timeout=180 if case.pressure or name == "transport_fault" else max(90, 45 * len(case.groups)))
    except subprocess.TimeoutExpired:
        case.errors.append("parent timeout")
        case.runtime.mark_forced_stop()
        case.forced_stop = True
        os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate()
    watching_done.set()
    for handle in case.output_handles: handle.close()
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
    retained_ipc = retained_ipc_paths(scratch) if cancelled else []
    # Cancellation is asynchronous. Observe bounded termination without killing
    # children on the candidate's behalf; persistent orphans still fail below.
    while cancelled and (child_alive or retained_ipc) and time.monotonic() - cleanup_started < 6:
        time.sleep(0.05)
        child_alive = live_children()
        retained_ipc = retained_ipc_paths(scratch)
    cleanup_wait = time.monotonic() - cleanup_started
    if retained_ipc:
        case.errors.append(f"communication IPC nodes remain after cancellation: {retained_ipc}")
    if child_alive:
        case.errors.append(f"child processes still alive: {child_alive}")
        for pid in child_alive:
            try:
                # Never perform a privileged kill on a candidate-reported PID.
                subprocess.run(["/usr/bin/python3", "-I", str(Path(__file__).with_name("worker_exec.py")),
                                "--kill", str(pid)], env={"PATH": "/usr/bin:/bin"}, check=False)
            except ProcessLookupError:
                pass
    runtime_result = case.runtime.finish({f"{g}/{r}": pid for (g, r), pid in case.pids.items()}, cancelled=cancelled)
    case.errors.extend(runtime_result["violations"])
    case.infrastructure_errors.extend(runtime_result["infrastructure_errors"])
    resource_result = None
    if case.resources:
        case.exclude_observer_ports()
        resource_result = case.resources.finish(cancelled=cancelled)
        case.errors.extend(resource_result["violations"])
        case.infrastructure_errors.extend(resource_result["infrastructure_errors"])
        case.resources.restore_faults()
    with case.condition:
        case.closed = True
        case.condition.notify_all()
    server.shutdown()
    server.server_close()
    expected_actors = {("one", "ROOT")} | {(g, r) for g in case.groups for r in case.roles}
    processes_ok = expected_actors == case.pids.keys() and len(set(case.pids.values())) == len(expected_actors)
    required_actors = expected_actors.copy()
    completion_ok = required_actors <= case.completed
    if name in ["cancellation", "cancel_queued"]:
        completion_ok = cancelled and not child_alive
    if not cancelled:
        for item in case.ledger.values():
            if item["accepted"] is True and item["first_seen"] is None:
                case.errors.append("accepted message absent when the dispatch finished")
            if item["accepted"] is False and item["first_seen"] is not None:
                case.errors.append("rejected message appeared in recipient input")
    leftovers = list((scratch / "tmp").glob("pi-team-*"))
    # Unclassified regular files/directories remain diagnostic. IPC node types
    # above have a cleanup assertion independent of storage names or formats.
    passed = processes_ok and completion_ok and not case.errors and not case.infrastructure_errors and (cancelled or proc.returncode == 0)
    result = {"name": name, "passed": passed, "exit_code": proc.returncode, "errors": case.errors,
              "actors": {f"{g}/{r}": pid for (g, r), pid in case.pids.items()},
              "observed": sorted(f"{g}/{r}" for g, r in case.observed),
              "completed": sorted(f"{g}/{r}" for g, r in case.completed),
              "diagnostic_retained_paths": [str(p) for p in leftovers],
              "retained_ipc_paths": retained_ipc,
              "cleanup_wait_seconds": round(cleanup_wait, 3),
              "elapsed_seconds": round(time.monotonic() - started, 2), "coverage": case.coverage,
              "infrastructure_errors": case.infrastructure_errors,
              "runtime_observation": runtime_result, "resource_observation": resource_result,
              "message_ledger": list(case.ledger.values()), "forced_stop": case.forced_stop, "teardown_diagnostics": case.teardown_diagnostics}
    if cleanup_observer is not None:
        # Optional curator-side observation before harness teardown deletes the
        # disposable tree. Never used by the generic scoring entrypoint, and
        # never exposed as a required interface in a candidate implementation.
        result["resource_review"] = cleanup_observer(case, scratch)
    for filename, value in [("result.json", result), ("requests.json", case.requests), ("events.json", case.events)]:
        with (directory / filename).open("w") as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
    if name == "cancel_queued" and passed:
        # Reuse HOME, TMPDIR, workspace and task addresses without deleting any
        # candidate state. Only the scenario's model responses start afresh.
        fresh = Case("direct")
        fresh.ids = dict(case.ids)
        fresh.stale_payloads = [p for values in case.payloads.values() for p in values] + list(case.replies.values())
        followup = _run_case("after_cancel", repo, directory, fresh, scratch=scratch)
        result["after_cancel"] = followup
        result["passed"] = followup["passed"]
        (directory / "result.json").write_text(json.dumps(result, ensure_ascii=True, indent=2))
        return result
    # The tree is candidate-owned; shutil.rmtree uses fd-based symlink protection.
    shutil.rmtree(scratch)
    return result


def run_case(name, repo, output):
    case = Case(name)
    try:
        return _run_case(name, repo, output, case)
    except Exception as exc:
        with case.condition:
            case.closed = True
            case.condition.notify_all()
        cleanup_errors = []
        if case.proc is not None and case.proc.poll() is None:
            try:
                os.killpg(case.proc.pid, signal.SIGKILL)
                case.proc.communicate(timeout=5)
            except Exception as cleanup_exc:
                cleanup_errors.append(repr(cleanup_exc))
        if hasattr(case, 'server'):
            try:
                case.server.shutdown()
                case.server.server_close()
            except Exception as cleanup_exc:
                cleanup_errors.append(repr(cleanup_exc))
        if case.runtime:
            try: case.runtime.finish({f"{g}/{r}": pid for (g, r), pid in case.pids.items()}, cancelled=True)
            except Exception as observer_exc: case.infrastructure_errors.append(repr(observer_exc))
        if case.resources:
            try: case.resources.restore_faults()
            except Exception as observer_exc: case.infrastructure_errors.append(repr(observer_exc))
        if not isinstance(exc, AssertionError): case.infrastructure_errors.append(repr(exc))
        else: case.errors.append(repr(exc))
        for handle in case.output_handles: handle.close()
        result = {'name': name, 'passed': False,
                  'errors': [*case.errors, *cleanup_errors], 'infrastructure_errors': case.infrastructure_errors}
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'result.json').write_text(json.dumps(result, indent=2))
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/workspace/pi"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier/text-behavior"))
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.cases:
        try:
            result = run_case(name, args.repo.resolve(), args.output)
        except Exception as exc:
            result = {"name": name, "passed": False, "errors": [], "infrastructure_errors": [repr(exc)]}
        results.append(result)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    summary = {"case_count": len(results), "passed": sum(r["passed"] for r in results),
               "status": "scoring_error" if any(r.get("infrastructure_errors") for r in results) else "scored",
               "external_model_calls": 0, "results": results}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if len(results) == len(args.cases) and all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
