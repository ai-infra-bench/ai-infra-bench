#!/usr/bin/env python3
"""Deterministic model input; real Pi tools, loop, provider adapters and persistence.

A trusted parent checks actual HTTP requests. It never imports candidate code,
rewrites candidate context, or supplies missing feature behavior.
"""
from __future__ import annotations
import argparse
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
import pwd
import re
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_observer_spec = importlib.util.spec_from_file_location("context_runtime_observer", Path(__file__).with_name("runtime_observer.py"))
_observer_module = importlib.util.module_from_spec(_observer_spec)
_observer_spec.loader.exec_module(_observer_module)
RuntimeObserver, ScoringError = _observer_module.RuntimeObserver, _observer_module.ScoringError
NoUnusedProviderObservation = _observer_module.NoUnusedProviderObservation


def public_events(observations):
    """Compatibility projection of independently sampled native public facts."""
    result = []
    for envelope in observations:
        fact = envelope["fact"]
        kind = fact["kind"]
        if kind == "session_start":
            result.append({"type": "session", "id": fact["session_id"], "file": fact.get("session_file")})
        elif kind == "provider_request":
            result.append({"type": "request_session", "id": fact["session_id"]})
        elif kind in ("tool_execution_end", "session_compact_failed"):
            result.append(fact["event"])
        elif kind == "compaction_attempt":
            result.append({"type": kind, "reason": fact.get("reason")})
        elif kind == "session_compact":
            result.append({"type": kind, "reason": fact.get("reason"), "from_extension": fact.get("from_extension")})
    return result

CASES = ["ordinary", "default_activation", "empty", "rollover", "repeated", "resume", "notes", "notes_overlap", "history", "history_all", "history_browse", "history_case", "history_literal", "batch", "pending_input", "isolation", "responses", "clear_resume", "repeated_unchanged"]
CAPACITY_CASES = ["capacity_notes", "capacity_empty", "capacity_clear", "capacity_jump", "capacity_idle", "capacity_pending", "capacity_headroom", "capacity_batch", "capacity_compaction",
                  "capacity_system_tools", "capacity_carried_notes", "capacity_configured_headroom", "capacity_idle_rpc",
                  "capacity_oversized_notes", "capacity_oversized_input", "capacity_legal_flags"]
REMINDER_BOUNDARY_CASES = ("capacity_reminder_boundary", "capacity_reminder_boundary_wide")
CAPACITY_CASES += REMINDER_BOUNDARY_CASES
INVALID_FLAG_CASES = ["capacity_invalid_zero", "capacity_invalid_order", "capacity_invalid_headroom"]
CASES += CAPACITY_CASES
CASES += INVALID_FLAG_CASES
CASES += ["thinking_search", "thinking_read"]
TOOLS = {"new_context", "notes_write", "notes_read", "history_search", "history_read"}
RUN_TIMEOUT_SECONDS = 90
def configuration(name):
    invalid = {
        "capacity_invalid_zero": ["--context-reminder-tokens", "0", "--context-rollover-tokens", "10", "--context-response-headroom", "1"],
        "capacity_invalid_order": ["--context-reminder-tokens", "10", "--context-rollover-tokens", "10", "--context-response-headroom", "1"],
        "capacity_invalid_headroom": ["--context-reminder-tokens", "1", "--context-rollover-tokens", "2", "--context-response-headroom", "50000"],
    }
    if name in invalid:
        return {"arguments": invalid[name], "provider": {"context_window": 50000, "max_tokens": 1}}
    if name in ("ordinary", "default_activation"):
        return {}
    if name not in CAPACITY_CASES:
        return {"arguments": [
            "--context-reminder-tokens", "700000",
            "--context-rollover-tokens", "800000",
            "--context-response-headroom", "100000",
        ]}
    config = {
        "arguments": [
            "--context-reminder-tokens", "40000",
            "--context-rollover-tokens", "150000",
            "--context-response-headroom", "4096",
        ],
        "capacity": {"evidence_chars": 240000, "burst_chars": 1000000},
    }
    if name == "capacity_headroom":
        config["arguments"][3] = "900000"
        config["arguments"][-1] = "250000"
        config["provider"] = {"context_window": 500000, "max_tokens": 250000}
    if name == "capacity_idle":
        config["provider"] = {"context_window": 1000000, "max_tokens": 300000}
    if name == "capacity_compaction":
        config["provider"] = {"context_window": 100000, "max_tokens": 4096}
        config["capacity"]["burst_chars"] = 500000
        config["files"] = {"agent/settings.json": '{"compaction":{"enabled":true,"reserveTokens":60000,"keepRecentTokens":10000},"retry":{"enabled":false}}'}
    if name == "capacity_system_tools":
        config["arguments"] = ["--context-reminder-tokens", "30000", "--context-rollover-tokens", "50000",
                               "--context-response-headroom", "4096"]
        config["provider"] = {"context_window": 100000, "max_tokens": 8192}
        config["environment"] = {"PI_CONTEXT_TEST_TOOL_PADDING": "60000"}
    if name == "capacity_carried_notes":
        config["arguments"] = ["--context-reminder-tokens", "15000", "--context-rollover-tokens", "45000",
                               "--context-response-headroom", "4096"]
        config["provider"] = {"context_window": 100000, "max_tokens": 8192}
    if name == "capacity_configured_headroom":
        config["arguments"] = ["--context-reminder-tokens", "200000", "--context-rollover-tokens", "390000",
                               "--context-response-headroom", "100000"]
        config["provider"] = {"context_window": 500000, "max_tokens": 250000}
        config["capacity"]["evidence_chars"] = 1200000
    if name in ("capacity_oversized_notes", "capacity_oversized_input"):
        config["arguments"] = ["--context-reminder-tokens", "10000", "--context-rollover-tokens", "20000",
                               "--context-response-headroom", "4096"]
        config["provider"] = {"context_window": 50000, "max_tokens": 4096, "large_context_window": 500000,
                              "large_max_tokens": 8192}
    if name == "capacity_legal_flags":
        config["arguments"] = ["--context-reminder-tokens", "49990", "--context-rollover-tokens", "49991",
                               "--context-response-headroom", "1"]
        config["provider"] = {"context_window": 50000, "max_tokens": 1}
    if name in REMINDER_BOUNDARY_CASES:
        rollover, headroom = (12000, 1024) if name == "capacity_reminder_boundary" else (18000, 2048)
        config["arguments"] = ["--context-reminder-tokens", str(rollover - 2),
                               "--context-rollover-tokens", str(rollover),
                               "--context-response-headroom", str(headroom)]
        config["provider"] = {"context_window": rollover + headroom, "max_tokens": rollover}
    return config


def text(message):
    content = message.get("content", "")
    return content if isinstance(content, str) else "\n".join(p.get("text", "") for p in content or [])


def all_text(body):
    # Preserve actual newlines in strings while inspecting all model-input fields,
    # including arguments and IDs. JSON serialization would escape multiline notes.
    def strings(value):
        if isinstance(value, str): yield value
        elif isinstance(value, list):
            for item in value: yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values(): yield from strings(item)
    wire = body.get("_wire")
    value = wire if wire is not None else body["messages"]
    return "\n".join(strings(value))


def lossless_text_visible(body, expected):
    """Find intact text in individual model-input fields, including valid JSON.

    Keeping fields separate prevents unrelated fragments from being joined into
    a false match while still recognizing escaped, lossless representations.
    """
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
    value = body.get("_wire", body.get("messages", []))
    return any(notes_visible(item, expected) for item in strings(value))


def call(name, **arguments):
    return {"id": "call_" + uuid.uuid4().hex, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


def calls(*items):
    return {"tool_calls": [dict(item, index=i) for i, item in enumerate(items)]}


def result(body, call_id=None):
    # Guidance may legally follow the tool batch. Locate the requested result,
    # not a particular message position or an older result with the same value.
    matches = [message for message in body["messages"] if message["role"] == "tool"
               and (call_id is None or message.get("tool_call_id", "").split("|", 1)[0] == call_id)]
    assert matches and (call_id is None or len(matches) == 1), "Expected the requested tool result in the actual model request"
    payload = text(matches[-1])
    try:
        value = json.loads(payload)
    except ValueError as exc:
        raise AssertionError("Expected JSON tool result, received: " + payload[:240]) from exc
    assert isinstance(value, dict), "Expected a JSON object tool result"
    return value


def history_contains(value, expected):
    """Match intact original text, including inside losslessly encoded JSON.

    Do not join fragments, unescape invalid JSON, or normalize the evidence.
    Metadata layout is unspecified; inspect values without prescribing a schema.
    """
    if not isinstance(value, str):
        return False
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if expected in item:
                return True
            try:
                pending.append(json.loads(item))
            except (ValueError, RecursionError):
                pass
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return False


def notes_visible(value, expected):
    """Accept intact notes as plain text or valid JSON strings inside guidance.

    The statement does not prescribe seed formatting. Decode complete JSON
    literals only; do not join fragments or repair malformed escape sequences.
    """
    if expected in value:
        return True
    for match in re.finditer(r'"(?:[^"\\]|\\.)*"', value, re.DOTALL):
        if history_contains(match.group(0), expected):
            return True
    return False


class BaseMeterGap(ScoringError):
    """The fixed Base estimateTokens port encountered an unimplemented legal shape."""


def utf16_length(value):
    if not isinstance(value, str):
        raise BaseMeterGap(f"Expected string, got {type(value).__name__}")
    return len(value.encode("utf-16-le", "surrogatepass")) // 2


def js_json_stringify(value):
    """JSON.stringify for the JSON values used by observed tool arguments.

    Integer-index object keys follow JavaScript enumeration order. Unsupported
    Number shapes fail closed as a meter gap instead of silently using Python's
    different number formatting.
    """
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float)):
        return ecmascript_number_stringify(value)
    if isinstance(value, list):
        return "[" + ",".join(js_json_stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        def array_index(key):
            if not isinstance(key, str) or not re.fullmatch(r"0|[1-9][0-9]*", key):
                return None
            number = int(key)
            return number if number < 2**32 - 1 and str(number) == key else None
        indexed = sorted(((array_index(key), key) for key in value if array_index(key) is not None))
        ordinary = [key for key in value if array_index(key) is None]
        keys = [key for _, key in indexed] + ordinary
        return "{" + ",".join(js_json_stringify(key) + ":" + js_json_stringify(value[key]) for key in keys) + "}"
    raise BaseMeterGap(f"Unsupported observed JSON value: {type(value).__name__}")


@lru_cache(maxsize=128)
def ecmascript_number_stringify(value):
    """Serialize an observed JSON number with a trusted ECMAScript runtime."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BaseMeterGap(f"Expected JSON number, got {type(value).__name__}")
    if isinstance(value, float) and not math.isfinite(value):
        raise BaseMeterGap("Observed non-finite number is not legal JSON")
    node = next((path for path in ("/usr/local/bin/node", "/usr/bin/node", "/bin/node")
                 if Path(path).is_file() and os.access(path, os.X_OK)), None)
    if node is None:
        raise BaseMeterGap("Trusted ECMAScript runtime is unavailable")
    try:
        completed = subprocess.run(
            [node, "--input-type=commonjs", "--eval",
             'const fs=require("node:fs");process.stdout.write(JSON.stringify(Number(fs.readFileSync(0,"utf8"))))'],
            input=repr(value), text=True, capture_output=True, timeout=5, cwd="/tmp",
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaseMeterGap("Trusted ECMAScript number serialization failed") from exc
    encoded = completed.stdout
    if completed.returncode != 0 or not encoded or encoded == "null":
        raise BaseMeterGap("Trusted ECMAScript number serialization failed")
    return encoded


def estimate_content_chars(content):
    if isinstance(content, str):
        return utf16_length(content)
    if not isinstance(content, list):
        raise BaseMeterGap(f"Unsupported message content: {type(content).__name__}")
    chars = 0
    for block in content:
        if not isinstance(block, dict):
            raise BaseMeterGap("Observed content block is not an object")
        if block.get("type") == "text":
            chars += utf16_length(block.get("text", ""))
        elif block.get("type") == "image":
            chars += 4800
        else:
            raise BaseMeterGap(f"Unsupported observed content block: {block.get('type')!r}")
    return chars


def base_estimate_message(message):
    """Independent port of Base compaction.ts estimateTokens."""
    role = message.get("role")
    if role == "user":
        chars = estimate_content_chars(message.get("content"))
    elif role == "assistant":
        content = message.get("content")
        if not isinstance(content, list):
            raise BaseMeterGap("Observed assistant content is not an array")
        chars = 0
        for block in content:
            kind = block.get("type") if isinstance(block, dict) else None
            if kind == "text":
                chars += utf16_length(block.get("text", ""))
            elif kind == "thinking":
                chars += utf16_length(block.get("thinking", ""))
            elif kind == "toolCall":
                chars += utf16_length(block.get("name", ""))
                chars += utf16_length(js_json_stringify(block.get("arguments")))
            else:
                raise BaseMeterGap(f"Unsupported observed assistant block: {kind!r}")
    elif role in ("custom", "toolResult"):
        chars = estimate_content_chars(message.get("content"))
    elif role == "bashExecution":
        chars = utf16_length(message.get("command")) + utf16_length(message.get("output"))
    elif role in ("branchSummary", "compactionSummary"):
        chars = utf16_length(message.get("summary"))
    else:
        raise BaseMeterGap(f"Unsupported observed AgentMessage role: {role!r}")
    return (chars + 3) // 4


def base_observed_meter(context):
    """Meter actual E-observed AgentMessages plus exact effective setup text."""
    required = {"messages", "system_prompt", "tools", "tools_json", "model"}
    missing = required - set(context)
    if missing:
        raise BaseMeterGap("Observed context is missing: " + repr(sorted(missing)))
    try:
        parsed_tools = json.loads(context["tools_json"])
    except (TypeError, ValueError) as exc:
        raise BaseMeterGap("Observed exact tools_json is invalid") from exc
    if parsed_tools != context["tools"]:
        raise BaseMeterGap("Observed tools_json does not represent active tools")
    system = context["system_prompt"]
    tools_json = context["tools_json"]
    setup = base_estimate_message({"role": "user", "content": system + "\n" + tools_json})
    no_system = base_estimate_message({"role": "user", "content": "\n" + tools_json})
    no_tools = base_estimate_message({"role": "user", "content": system + "\n[]"})
    messages = sum(base_estimate_message(message) for message in context["messages"])
    return {"tokens": setup + messages, "messages": messages, "setup": setup,
            "system_contribution": setup - no_system, "tools_contribution": setup - no_tools}


def pair_check(body):
    pending = set()
    for message in body["messages"]:
        if message["role"] == "tool":
            assert message["tool_call_id"] in pending, "Orphan tool result in model request"
            pending.remove(message["tool_call_id"])
        else:
            assert not pending, "Tool calls missing results before next message"
            if message["role"] == "assistant":
                ids = [c["id"] for c in message.get("tool_calls", [])]
                assert len(ids) == len(set(ids)), "Repeated call IDs"
                pending.update(ids)
    assert not pending, "Unresolved tool calls in model request"


def normalize(body):
    if "messages" in body: return body
    messages = []
    if body.get("instructions"): messages.append({"role":"system", "content":body["instructions"]})
    for item in body["input"]:
        kind = item.get("type", "message")
        if kind == "message": messages.append({"role":item["role"],"content":item.get("content",[])})
        elif kind == "function_call":
            if not messages or messages[-1]["role"] != "assistant": messages.append({"role":"assistant","content":""})
            messages[-1].setdefault("tool_calls",[]).append({"id":item["call_id"],"function":{"name":item["name"],"arguments":item["arguments"]}})
        elif kind == "function_call_output": messages.append({"role":"tool","tool_call_id":item["call_id"],"content":item["output"]})
    return {"messages":messages,"tools":[{"function":t} for t in body.get("tools",[])],"_wire":body}


class Scenario:
    def __init__(self, name):
        self.name = name
        self.nonce = uuid.uuid4().hex
        self.goal = "Investigate timeout; preserve user instruction " + self.nonce
        self.consumed_users = [self.goal]
        self.correction = "Continue; keep the newly required compatibility constraint " + uuid.uuid4().hex
        self.system = "System invariant " + uuid.uuid4().hex
        self.summary = "缓存已排除。继续检查连接池。" + uuid.uuid4().hex
        self.hypothesis = "assistant-hypothesis-" + uuid.uuid4().hex + "\nUnconfirmed conclusion " + uuid.uuid4().hex
        self.anchor = "evidence-anchor-[a.b+?]-" + uuid.uuid4().hex
        self.argument_label = "request-label-" + uuid.uuid4().hex + ":" + uuid.uuid4().hex
        self.secret = "original-receipt-" + uuid.uuid4().hex
        self.evidence = {"old": self.anchor + "\n" + "古🙂e\u0301 log\n" * 800 + self.secret,
                         "noise": "unrelated-original-" + uuid.uuid4().hex + "\n" + "unrelated log\n" * 800,
                         "side": "SIDE-" + uuid.uuid4().hex,
                         "hold": "HELD-TOOL-" + uuid.uuid4().hex,
                         "before": "PRE-BATCH-" + uuid.uuid4().hex}
        if name == "history_literal":
            self.anchor = "tool-literal-" + uuid.uuid4().hex
            user_anchor = "user-literal-" + uuid.uuid4().hex
            quoted = 'second "quoted ' + uuid.uuid4().hex + '"'
            self.evidence["old"] = self.anchor + ": first\n" + quoted + " end-" + self.secret
            self.goal = user_anchor + ': remember\n"keep exact" tail-' + uuid.uuid4().hex
            self.consumed_users = [self.goal]
            self.literal_records = [
                (self.anchor, self.evidence["old"], ["first\nsecond", quoted]),
                (user_anchor, self.goal, ['remember\n"keep exact"', '"keep exact"']),
            ]
        if name == "history_all":
            self.shared_query = "shared-history-query-" + uuid.uuid4().hex
            self.history_keys = ["match_a", "match_b", "match_c"]
            for index, key in enumerate(self.history_keys):
                marker = "complete-original-%s-%s" % (index, uuid.uuid4().hex)
                self.evidence[key] = self.shared_query + "\n" + (chr(65 + index) * 700) + "\n" + marker
        self.current_marker = "new-window-assistant-" + uuid.uuid4().hex
        self.events, self.requests, self.errors, self.served, self.emitted = [], [], [], [], []
        self.ordinary_compaction_requests = []
        self.event_diagnostics, self.scoring_errors, self.observer_reports = [], [], []
        self.rpc_wait_errors = []
        self.observer = None
        self.previous_phase_events = []
        self.saved, self.checks = {}, []
        if name in REMINDER_BOUNDARY_CASES:
            self.saved["capacity_boundary"] = {
                "actual_required_request": None, "actual_meter": None, "coverage": "unresolved",
                "pending_prompt_sent": False, "turn_settled": False, "visible_errors": [],
            }
        self.done = False
        self.script = None
        self.hold_started = threading.Event()
        self.hold_release = threading.Event()
        self.configuration = configuration(name)
        if name in CAPACITY_CASES:
            self.capacity = self.configuration["capacity"]
            size = self.capacity["burst_chars"] if name == "capacity_jump" else self.capacity["evidence_chars"]
            self.evidence["old"] = self.anchor + "\n" + "M" * size + "\n" + self.secret
            for key in ["side", "hold"]:
                self.evidence[key] += "\n" + "X" * self.capacity["burst_chars"]
        if name == "capacity_system_tools":
            self.system = "System invariant " + self.nonce + "\n" + "S" * 60000
        if name == "capacity_carried_notes":
            self.summary = "carried-note-" + self.nonce + "\n" + "N" * 70000
        if name == "capacity_oversized_notes":
            self.summary = "oversized-note-" + self.nonce + "\n" + "O" * 220000
        if name == "capacity_oversized_input":
            self.correction = "oversized-unpresented-input-" + self.nonce + "\n" + "U" * 220000

    def result(self, body):
        # Native execution always has a recorded emitted call. The no-call
        # fallback supports isolated generator tests with synthetic tool results.
        call_id = self.emitted[-1]["id"] if self.emitted else None
        return result(body, call_id)

    def checked(self, name):
        self.checks.append({"name":name,"request":len(self.requests)})

    def check_fresh(self, body, *, notes=True):
        value = all_text(body)
        assert self.system in value, "System instructions lost"
        for original in self.consumed_users:
            if not (notes and original in self.summary):
                assert not lossless_text_visible(body, original), "Consumed user message remains outside working notes"
        if notes: assert notes_visible(value, self.summary), "Latest working notes not carried into fresh context"
        assert not lossless_text_visible(body, self.secret) and not lossless_text_visible(body, self.anchor), "Old evidence still in active context"
        assert not lossless_text_visible(body, self.evidence["noise"].splitlines()[0]), "Unrelated old record reloaded"
        assert not lossless_text_visible(body, self.hypothesis), "Old assistant text still in active context"
        old_calls = {item["id"] for item in self.emitted}
        for message in body["messages"]:
            if message["role"] == "assistant":
                assert not any(item.get("id") in old_calls for item in message.get("tool_calls", [])), "Earlier tool-call/result batch remains in fresh context"
            if message["role"] == "tool":
                call_id = message.get("tool_call_id", "").split("|", 1)[0]
                assert call_id not in old_calls, "Earlier tool-call/result batch remains in fresh context"
        self.checked("next_request_is_fresh")

    def initial(self, body):
        names = {t["function"]["name"] for t in body.get("tools", [])}
        if self.name == "ordinary": assert not (TOOLS & names), "Feature enabled without extension"
        else: assert TOOLS <= names, "Missing public tools: " + str(sorted(TOOLS - names))

    def setup_window(self):
        body = yield dict(calls(call("evidence", key="old", request_label=self.argument_label),call("evidence",key="noise")), content=self.hypothesis)
        assert self.secret in all_text(body), "Evidence never reached real model input"
        body = yield calls(call("notes_write", text=self.summary))
        body = yield calls(call("new_context"))
        self.check_fresh(body)
        return body

    def search_items(self, query):
        arguments, items = {"query": query}, []
        while True:
            body = yield calls(call("history_search", **arguments))
            page = self.result(body)
            items.extend(page["items"])
            cursor = page.get("next_cursor")
            arguments = {"query": query, "cursor": cursor} if cursor is not None else None
            if arguments is None:
                return body, items

    def recover_all(self, query, expected):
        found = {}
        arguments = {"query": query}
        while arguments is not None:
            body = yield calls(call("history_search", **arguments))
            page = self.result(body)
            for item in page["items"]:
                identity = {key: item[key] for key in ["window_id", "item_id"]}
                body = yield calls(call("history_read", **identity))
                value = self.result(body)["text"]
                for key, original in expected.items():
                    if key not in found and history_contains(value, original):
                        found[key] = identity
            cursor = page.get("next_cursor")
            arguments = {"query": query, "cursor": cursor} if cursor is not None else None
        missing = sorted(set(expected) - set(found))
        assert not missing, "Matching original texts not all reachable: " + repr(missing)
        return body, found

    def recover(self, query, expected, *, also=None):
        body, items = yield from self.search_items(query)
        assert items, "Search did not locate original record"
        # Metadata, search order and previews are not fixed by the contract.
        for item in items:
            identity = {key:item[key] for key in ["window_id","item_id"]}
            body = yield calls(call("history_read",**identity))
            value = self.result(body)["text"]
            if history_contains(value, expected) and (also is None or history_contains(value, also)):
                self.checked("original_record_recovered")
                return body, identity
        raise AssertionError("No matching item exposes the complete original record")

    def script_main(self, phase=0):
        body = yield
        self.initial(body)
        if self.name in CAPACITY_CASES:
            yield from self.script_capacity(body, phase)
            return
        if self.name == "ordinary":
            body = yield calls(call("evidence",key="side"))
            assert self.evidence["side"] in all_text(body)
            marker = "builtin-bash-" + self.nonce
            body = yield calls(call("bash", command="printf " + marker + " > builtin-output.txt; cat builtin-output.txt"))
            assert body["messages"][-1]["role"] == "tool", "Expected builtin Bash result"
            assert text(body["messages"][-1]) == marker, "Builtin Bash output changed while extension disabled"
            self.checked("disabled_builtin_bash_output")
        elif self.name == "default_activation":
            self.checked("default_activation_without_fixed_budget_values")
        elif self.name == "history_all":
            expected = {key: self.evidence[key] for key in self.history_keys}
            if phase == 0:
                body = yield calls(*(call("evidence", key=key) for key in self.history_keys))
                assert all(value in all_text(body) for value in expected.values()), "Shared-query originals did not enter real model input"
                body = yield calls(call("new_context"))
                self.check_fresh(body, notes=False)
                body, self.saved["history_all"] = yield from self.recover_all(self.shared_query, expected)
                body = yield calls(call("evidence", key="side"))
                assert self.evidence["side"] in all_text(body), "Normal tool use did not append after history traversal"
                self.checked("all_shared_query_originals_recovered")
            else:
                for key, identity in self.saved["history_all"].items():
                    body = yield calls(call("history_read", **identity))
                    assert history_contains(self.result(body)["text"], expected[key]), "Old history identity failed after reopening"
                body, reopened = yield from self.recover_all(self.shared_query, expected)
                assert set(reopened) == set(expected), "Reopened search lost shared-query originals"
                self.checked("shared_query_history_and_old_ids_survive_reopen")
        elif self.name == "empty":
            # No notes_write prerequisite, even when there is old work to discard.
            body = yield dict(calls(call("evidence", key="old"), call("evidence", key="noise")), content=self.hypothesis)
            assert self.secret in all_text(body), "Evidence never reached real model input"
            body = yield calls(call("new_context"))
            self.check_fresh(body,notes=False)
            body, _ = yield from self.recover(self.anchor, self.evidence["old"])
            body = yield calls(call("evidence",key="side"))
            assert self.evidence["side"] in all_text(body)
        elif self.name == "clear_resume":
            if phase == 0:
                body = yield from self.setup_window()
                body, self.saved["identity"] = yield from self.recover(self.anchor,self.evidence["old"])
                self.saved["old_note"] = self.summary
                self.summary = ""
                body = yield calls(call("notes_write",text=""))
                body = yield calls(call("notes_read"))
                assert self.result(body)["text"] == "", "Empty replacement did not clear working notes"
                body = yield calls(call("new_context"))
                self.check_fresh(body,notes=False)
                assert self.saved["old_note"] not in all_text(body), "Cleared conclusion resurrected on reset"
            else:
                self.check_fresh(body,notes=False)
                assert self.saved["old_note"] not in all_text(body), "Cleared conclusion resurrected on restart"
                body = yield calls(call("notes_read"))
                assert self.result(body)["text"] == "", "Cleared notes not persisted"
                body = yield calls(call("history_read",**self.saved["identity"]))
                assert history_contains(self.result(body)["text"], self.evidence["old"]), "Clearing working notes destroyed original evidence"
                self.checked("empty_note_replacement_survives_restart_without_erasing_history")
        elif phase == 1:
            if self.name == "resume":
                value=all_text(body)
                assert notes_visible(value, self.summary) and self.current_marker in value, "Resume lost notes or current-window conversation"
                assert self.correction in value and self.secret not in value, "Resume lost correction or restored discarded history"
                body = yield calls(call("notes_read"))
                assert self.result(body)["text"] == self.summary
                body = yield calls(call("history_read",**self.saved["identity"]))
                assert history_contains(self.result(body)["text"], self.evidence["old"]), "IDs/evidence did not survive real process restart"
                self.consumed_users.append(self.correction)
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                body, _ = yield from self.recover(self.correction.split()[-1], self.correction)
                self.checked("restart_restores_active_state_and_stable_history")
            else:
                value=all_text(body)
                assert self.summary not in value and self.secret not in value
                body = yield calls(call("notes_read"))
                assert self.summary not in all_text(body), "Notes leaked into second session"
                body, items = yield from self.search_items(self.anchor)
                # The current search call can itself contain this query. Inspect
                # returned records instead of imposing an empty-result convention.
                for item in items:
                    identity={k:item[k] for k in ["window_id","item_id"]}
                    body = yield calls(call("history_read",**identity))
                    assert not history_contains(self.result(body)["text"], self.secret), "Other session's original record is searchable"
                body = yield calls(call("history_read",**self.saved["identity"]))
                assert self.secret not in all_text(body), "Foreign history IDs reveal another session's content"
                self.checked("same_directory_sessions_are_independent")
        elif self.name in ["rollover","repeated","resume","isolation","responses"]:
            body = yield from self.setup_window()
            if self.name == "repeated":
                for _ in range(2):
                    previous=self.summary
                    self.summary="Updated conclusion "+uuid.uuid4().hex
                    body = yield calls(call("notes_write",text=self.summary))
                    body = yield calls(call("new_context"))
                    self.check_fresh(body)
                    assert previous not in all_text(body), "Stale working note resurrected"
            # Continue with a normal tool call, proving pairing and new-window accumulation.
            body = yield dict(calls(call("evidence",key="side")),content=self.current_marker)
            assert self.current_marker in all_text(body) and self.evidence["side"] in all_text(body)
            self.checked("new_window_continues_normal_tool_loop")
            body, self.saved["identity"] = yield from self.recover(self.anchor,self.evidence["old"])
            assert self.evidence["noise"].splitlines()[0] not in all_text(body), "Reading one record reloads unrelated history"
            if self.name in ["rollover","responses"]:
                body,_=yield from self.recover(self.hypothesis.splitlines()[0],self.hypothesis)
                body,_=yield from self.recover(self.nonce,self.goal)
            if self.name == "resume":
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                body = yield dict(calls(call("notes_read")),content=self.current_marker)
                assert self.result(body)["text"] == self.summary
        elif self.name == "repeated_unchanged":
            # Reproduce the live model's repeated reset pattern, without judging
            # its strategy or requiring the extension to rewrite working notes.
            self.summary += "\n下一步调用 new_context，然后继续核验。"
            body = yield from self.setup_window()
            body, identity = yield from self.recover(self.anchor, self.evidence["old"])
            for index in range(10):
                marker = "between-resets-" + uuid.uuid4().hex
                body = yield dict(calls(call("notes_read")), content=marker)
                assert self.result(body)["text"] == self.summary, "Repeated reset changed working notes"
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                assert marker not in all_text(body), "Repeated reset retained intervening assistant text"
            body = yield calls(call("notes_read"))
            assert self.result(body)["text"] == self.summary, "Unchanged working notes lost after eleven resets"
            body = yield calls(call("history_read", **identity))
            assert history_contains(self.result(body)["text"], self.evidence["old"]), "Old evidence/IDs lost after eleven resets"
            body = yield calls(call("evidence", key="side"))
            assert self.evidence["side"] in all_text(body), "Tool loop stopped after repeated resets"
            self.checked("eleven_resets_preserve_unchanged_notes_and_original_evidence")
        elif self.name == "notes":
            self.summary="进展🙂e\u0301\n"*700
            body = yield calls(call("notes_write",text=self.summary))
            body = yield calls(call("notes_read"))
            assert self.result(body)["text"] == self.summary, "Working notes changed or truncated"
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            previous=self.summary
            self.summary="替换后的结论\n"+uuid.uuid4().hex
            body = yield calls(call("notes_write",text=self.summary))
            body = yield calls(call("notes_read"))
            assert self.result(body)["text"] == self.summary, "Write did not replace notes"
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            assert previous not in all_text(body)
        elif self.name == "pending_input":
            body = yield from self.setup_window()
            body = yield calls(call("new_context"), call("evidence", key="hold"))
            self.check_fresh(body)
            assert self.correction in all_text(body), "User input queued during the tool batch was discarded"
            assert self.evidence["hold"] not in all_text(body), "Completed outgoing tool output remains in fresh context"
            assert self.hold_release.is_set(), "Continuation preceded completion of the held tool"
            self.consumed_users.append(self.correction)
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            body, _ = yield from self.recover(self.correction.split()[-1], self.correction)
            self.checked("pending_user_survives_reset_then_enters_normal_history")
        elif self.name == "notes_overlap":
            alternatives = ["First whole replacement " + uuid.uuid4().hex,
                            "Second whole replacement " + uuid.uuid4().hex]
            body = yield calls(*(call("notes_write", text=value) for value in alternatives))
            body = yield calls(call("notes_read"))
            chosen = self.result(body)["text"]
            assert chosen in alternatives, "Overlapping writes merged or corrupted complete note values"
            # Either declared ordering can be valid. Once observable, that saved
            # value must survive a reset; do not prescribe scheduler order.
            self.summary = chosen
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            self.summary = "Later sequential replacement " + uuid.uuid4().hex
            body = yield calls(call("notes_write", text=self.summary))
            body = yield calls(call("notes_read"))
            assert self.result(body)["text"] == self.summary, "Later successful write did not replace prior batch"
            self.checked("complete_overlapping_replacements_and_later_write")
        elif self.name == "history_browse":
            body = yield calls(call("evidence", key="old"))
            body = yield calls(call("new_context"))
            self.check_fresh(body, notes=False)
            body, items = yield from self.search_items("")
            assert items, "Empty query did not browse available history"
            found = False
            for item in items:
                identity = {key:item[key] for key in ["window_id", "item_id"]}
                body = yield calls(call("history_read", **identity))
                if history_contains(self.result(body)["text"], self.goal):
                    found = True
                    break
            assert found, "Empty-query browsing did not expose the original user record"
            self.checked("empty_query_browses_history_after_no_note_reset")
        elif self.name == "history_case":
            body = yield from self.setup_window()
            body, target = yield from self.recover(self.anchor, self.evidence["old"])
            body, items = yield from self.search_items(self.anchor.upper())
            for item in items:
                identity = {key:item[key] for key in ["window_id", "item_id"]}
                assert identity != target, "Case-mismatched query returned the nonmatching original"
                # Other matches, including the search call itself, are legal.
                body = yield calls(call("history_read", **identity))
                assert not history_contains(self.result(body)["text"], self.evidence["old"]), "Case-mismatched query exposes the original as a match"
            self.checked("literal_search_distinguishes_case")
        elif self.name == "history_literal":
            body = yield calls(call("evidence", key="old"))
            assert self.evidence["old"] in all_text(body), "Literal original never entered real model input"
            body = yield calls(call("new_context"))
            self.check_fresh(body, notes=False)
            targets = []
            # Independent anchors locate the originals before any literal
            # searches or reads can copy their complete contents into history.
            for anchor, original, queries in self.literal_records:
                body, identity = yield from self.recover(anchor, original)
                targets.append((identity, original, queries))
            for identity, original, queries in targets:
                for query in queries:
                    assert query != original, "Literal fixture must query a proper substring"
                    body, items = yield from self.search_items(query)
                    identities = [{key: item[key] for key in ("window_id", "item_id")} for item in items]
                    assert identity in identities, "Literal query omitted the original record identity"
                    body = yield calls(call("history_read", **identity))
                    assert history_contains(self.result(body)["text"], original), "Literal history read lost complete original text"
                negative_queries = [queries[0].upper(),
                                    queries[0].replace("\n", "\\n"),
                                    queries[1].replace('"', '\\"')]
                for query in negative_queries:
                    assert query not in original, "Negative literal fixture unexpectedly matches original"
                    body, items = yield from self.search_items(query)
                    identities = [{key: item[key] for key in ("window_id", "item_id")} for item in items]
                    assert identity not in identities, "Nonmatching literal query returned the original identity"
                    # New search/read records can legally contain encoded copies
                    # of this original. Their distinct identities are allowed.
            self.checked("literal_newlines_and_quotes_match_original_identities")
        elif self.name in ["thinking_search", "thinking_read"]:
            # A standard reasoning-capable API response is parsed and journaled
            # by Pi itself; the fixture never inserts an internal message.
            anchor = "reasoning-anchor-" + uuid.uuid4().hex
            reasoning = anchor + "\n先排除重试🙂e\u0301，再检查连接池。\n" + uuid.uuid4().hex
            body = yield dict(calls(call("evidence", key="side")),
                              content=self.hypothesis, reasoning_content=reasoning)
            body = yield calls(call("new_context"))
            self.check_fresh(body, notes=False)
            assert not lossless_text_visible(body, anchor), "Old assistant reasoning remains in active context"
            # Search once by reasoning and independently by visible text. The
            # complete reasoning and visible text must belong to the same record;
            # a later search call containing just the query cannot satisfy this.
            query = anchor if self.name == "thinking_search" else self.hypothesis
            body, _ = yield from self.recover(query, reasoning, also=self.hypothesis)
            self.checked("original_assistant_reasoning_and_visible_text_recovered")
        elif self.name == "history":
            body = yield from self.setup_window()
            # A receipt near the end of a long record must lead back to that record.
            body,_=yield from self.recover(self.secret,self.evidence["old"])
            assert self.evidence["noise"].splitlines()[0] not in all_text(body)
            body,_=yield from self.recover(self.hypothesis.splitlines()[0],self.hypothesis)
            # Verify original assistant tool arguments, not only prose.
            body,identity=yield from self.recover(self.argument_label.split(":")[0], self.argument_label)
            assert history_contains(self.result(body)["text"], "evidence"), "Assistant tool-call name was not archived"
        elif self.name == "batch":
            body = yield from self.setup_window()
            body = yield calls(call("evidence", key="before"))
            assert self.evidence["before"] in all_text(body), "Pre-batch evidence never entered real model input"
            previous=self.summary
            self.summary="Evidence discovered in the switching batch "+uuid.uuid4().hex
            batch=[call("new_context"),call("evidence",key="side"),call("notes_write",text=self.summary),call("new_context")]
            body = yield calls(*batch)
            self.check_fresh(body)
            assert previous not in all_text(body)
            assert not lossless_text_visible(body, self.evidence["before"]), "Pre-batch evidence retained in the new window"
            assert self.evidence["side"] not in all_text(body), "Switching batch output retained in the new window"
            assert self.served.count("side")==1, "Requested side-effect tool skipped or repeated"
            for requested in batch:
                ends=[e for e in self.events if e.get("type")=="tool_execution_end" and e.get("toolCallId","").split("|")[0]==requested["id"]]
                assert len(ends)==1 and not ends[0]["isError"], "Batch did not complete each requested tool exactly once"
            body=yield calls(call("notes_read"))
            assert self.result(body)["text"]==self.summary
            body, outgoing = yield from self.recover(self.evidence["before"].split("-")[-1], self.evidence["before"])
            body, archived = yield from self.recover(self.evidence["side"].split("-")[-1],self.evidence["side"])
            assert archived["window_id"] == outgoing["window_id"], "Switching batch result was assigned to a different history window"
            self.checked("whole_batch_committed_before_transition")
        else: raise AssertionError("Unimplemented scenario")
        self.done=True
        yield {"content":"VERIFIED-"+self.nonce}

    def script_capacity(self, body, phase):
        if self.name in REMINDER_BOUNDARY_CASES:
            yield from self.script_reminder_boundary(body)
            return

        def reminder_messages(request):
            return [message for message in request["_observed_context"]["messages"]
                    if message.get("role") == "custom" and message.get("customType") == "context_capacity_reminder"]

        def reminders(request):
            messages = reminder_messages(request)
            for message in messages:
                notice = text(message)
                value = json.loads(notice)
                assert type(value.get("remaining_tokens")) is int and value["remaining_tokens"] >= 0, "Reminder lacks remaining capacity"
                assert isinstance(value.get("message"), str) and value["message"].strip(), "Reminder lacks model guidance"
                assert notice in all_text(request), "Reminder event did not enter actual model input"
            return len(messages)

        if phase == 0 and self.name != "capacity_system_tools":
            assert not reminders(body), "Reminder issued below the documented threshold for initial fixture input"

        if self.name == "capacity_system_tools":
            meter = body["_base_meter"]
            assert meter["tokens"] >= 30000, "Effective system and active tools did not reach the reminder boundary"
            assert meter["tokens"] - meter["system_contribution"] < 30000, "System prompt was not decisive"
            assert meter["tokens"] - meter["tools_contribution"] < 30000, "Active tool definitions were not decisive"
            assert reminders(body) == 1, "Expected exactly one first-window reminder"
            first_reminder = reminder_messages(body)[0]
            body = yield calls(call("notes_read"))
            second_reminders = reminder_messages(body)
            assert len(second_reminders) <= 1, "Reminder duplicated within one window"
            if second_reminders:
                assert text(second_reminders[0]) == text(first_reminder), "Reminder content changed within one window"
            body = yield calls(call("new_context"))
            self.check_fresh(body, notes=False)
            assert reminders(body) == 1, "New window did not receive its own single reminder"
            self.checked("system_tools_meter_and_once_per_window_reminder")
        elif self.name == "capacity_carried_notes":
            assert body["_base_meter"]["tokens"] < 15000, "Initial fixture unexpectedly reached reminder boundary"
            body = yield calls(call("notes_write", text=self.summary))
            assert lossless_text_visible(body, self.summary), "Saved notes were not present before explicit reset"
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            assert 15000 <= body["_base_meter"]["tokens"] < 45000, "Carried notes did not decide the configured capacity boundary"
            assert reminders(body) == 1, "Fresh window did not count carried notes toward its reminder"
            self.checked("carried_notes_are_metered_in_fresh_window")
        elif self.name == "capacity_configured_headroom":
            assert body["_base_meter"]["tokens"] < 200000
            body = yield calls(call("evidence", key="old"))
            assert self.secret in all_text(body), "Reset below the configured-headroom boundary"
            assert 250000 <= body["_base_meter"]["tokens"] < 400000, "Fixture did not distinguish model maxTokens from configured headroom"
            assert reminders(body), "Expected reminder below configured rollover"
            self.checked("configured_headroom_is_independent_of_model_max_tokens")
        elif self.name == "capacity_idle_rpc":
            if not self.saved.get("idle_completed"):
                self.saved["idle_completed"] = True
                body = yield {"content": self.current_marker + "\n" + "I" * self.capacity["burst_chars"]}
            self.check_fresh(body, notes=False)
            assert self.correction in all_text(body), "New same-process user input lost on idle rollover"
            assert self.current_marker not in all_text(body), "Finished prior response retained after same-process idle rollover"
            assert not reminders(body), "Rollover emitted a lower-priority reminder"
            self.checked("same_rpc_process_idle_then_new_prompt_rolls_over")
        elif self.name == "capacity_oversized_notes":
            if not self.saved.get("oversized_attempted"):
                self.saved["oversized_attempted"] = True
                body = yield calls(call("notes_write", text=self.summary))
            assert "recovery_prompt" in self.saved, "Oversized notes reached HTTP before public model recovery"
            self.check_fresh(body)
            assert self.saved["recovery_prompt"] in all_text(body), "Recovery prompt did not reach the larger model"
            headroom = int(self.configuration["arguments"][self.configuration["arguments"].index("--context-response-headroom") + 1])
            assert body["_base_meter"]["tokens"] < body["_observed_context"]["model"]["contextWindow"] - headroom, \
                "Recovered notes still exceed the current public model"
            self.checked("oversized_notes_error_then_same_process_model_recovery")
        elif self.name == "capacity_oversized_input":
            if not self.saved.get("oversized_attempted"):
                self.saved["oversized_attempted"] = True
                body = yield {"content": self.current_marker + "\n" + "I" * self.capacity["burst_chars"]}
            assert "recovery_prompt" in self.saved, "Oversized unpresented input reached HTTP before public model recovery"
            self.check_fresh(body, notes=False)
            assert self.correction in all_text(body), "Oversized unpresented input was discarded"
            assert self.saved["recovery_prompt"] in all_text(body), "Recovery prompt did not reach the larger model"
            assert self.current_marker not in all_text(body), "Prior finished response survived oversized-input rollover"
            headroom = int(self.configuration["arguments"][self.configuration["arguments"].index("--context-response-headroom") + 1])
            assert body["_base_meter"]["tokens"] < body["_observed_context"]["model"]["contextWindow"] - headroom, \
                "Recovered input still exceeds the current public model"
            self.checked("oversized_unpresented_input_error_then_same_process_model_recovery")
        elif self.name == "capacity_legal_flags":
            assert body["_base_meter"]["tokens"] < 49990, "Adjacent legal flag fixture unexpectedly crossed its threshold"
            assert not reminders(body), "Adjacent legal flags emitted an early reminder"
            self.checked("positive_adjacent_public_flags_are_accepted")
        if self.name == "capacity_idle":
            if phase == 0:
                self.done = True
                yield {"content": "VERIFIED-" + self.nonce + "\n" + self.current_marker + "\n" + "I" * self.capacity["burst_chars"]}
                return
            self.check_fresh(body, notes=False)
            assert self.correction in all_text(body), "New user input lost on idle/reopen rollover"
            assert self.current_marker not in all_text(body), "Finished prior response retained across automatic reset"
            assert not reminders(body), "Jump emitted reminder alongside rollover"
            # Exclude the oversized final answer, which also contains the
            # completion nonce. Reading irrelevant huge records can itself
            # legitimately roll over and must not impose search ordering.
            body, _ = yield from self.recover(self.goal.split("; ", 1)[1], self.goal)
            self.checked("idle_does_not_continue_but_next_user_turn_rolls_over")
        elif self.name not in ("capacity_system_tools", "capacity_carried_notes", "capacity_configured_headroom",
                                "capacity_idle_rpc", "capacity_oversized_notes", "capacity_oversized_input",
                                "capacity_legal_flags"):
            body = yield dict(calls(call("evidence", key="old")), content=self.hypothesis)
            if self.name == "capacity_jump":
                self.check_fresh(body, notes=False)
                assert not reminders(body), "Jump emitted reminder alongside rollover"
                self.checked("jump_rolls_over_without_notes_or_reminder")
            else:
                first_reminders = reminders(body)
                assert first_reminders, "No reminder between documented configured thresholds"
                assert self.secret in all_text(body), "Reminder prematurely discarded context"
                has_notes = self.name in ("capacity_notes", "capacity_clear", "capacity_pending", "capacity_batch")
                body = yield calls(call("notes_write", text=self.summary) if has_notes else call("notes_read"))
                if not has_notes:
                    assert self.result(body)["text"] == ""
                # An existing reminder may remain in context. Count additions,
                # not mere presence, to avoid requiring an ephemeral reminder.
                assert reminders(body) <= first_reminders, "Reminder duplicated in the same window"
                if self.name == "capacity_clear":
                    self.saved["old_note"] = self.summary
                    self.summary = ""
                    body = yield calls(call("notes_write", text=""))
                    assert reminders(body) <= first_reminders, "Reminder duplicated after clearing notes"
                pending = self.name == "capacity_pending"
                batch = None
                if self.name == "capacity_batch":
                    previous = self.summary
                    self.summary = "Latest successful note in the automatic switching batch " + uuid.uuid4().hex
                    batch = [call("evidence", key="side"), call("notes_write", text=self.summary), call("evidence", key="before")]
                    body = yield calls(*batch)
                    assert previous not in all_text(body), "Automatic reset used notes from before the batch"
                    for requested in batch:
                        ends = [event for event in self.events if event.get("type") == "tool_execution_end" and event.get("toolCallId", "").split("|")[0] == requested["id"]]
                        assert len(ends) == 1 and not ends[0]["isError"], "Automatic reset did not finish every batch tool exactly once"
                else:
                    body = yield calls(call("evidence", key="hold" if pending else "side"))
                self.check_fresh(body, notes=self.name in ("capacity_notes", "capacity_pending", "capacity_batch"))
                assert self.evidence["side"][:37] not in all_text(body)
                assert not reminders(body), "Rollover also emitted the lower-threshold reminder"
                if self.name == "capacity_clear":
                    assert self.saved["old_note"] not in all_text(body), "Cleared notes resurrected"
                    body = yield calls(call("notes_read"))
                    assert self.result(body)["text"] == "", "Automatic reset replaced explicitly cleared notes with fallback content"
                if pending:
                    assert self.correction in all_text(body), "Queued input lost during automatic reset"
                    assert self.evidence["hold"][:37] not in all_text(body)
                    self.consumed_users.append(self.correction)
                    body = yield calls(call("evidence", key="side"))
                    self.check_fresh(body)
                    body, _ = yield from self.recover(self.correction.split()[-1], self.correction)
                    self.checked("automatic_rollover_preserves_pending_input_then_archives_it")
                else:
                    if self.name == "capacity_compaction":
                        # A legal lossless history representation can be larger
                        # than the original pressure payload and trigger another
                        # rollover. Recover a small archived original instead;
                        # do not impose representation size/order on history.
                        body, _ = yield from self.recover(self.goal.split("; ", 1)[1], self.goal)
                        # Independently exercise the new window's reminder with
                        # one known-size ordinary tool output, not history JSON.
                        body = yield calls(call("evidence", key="old"))
                        assert self.evidence["old"] in all_text(body), "Fresh-window evidence did not reach model input"
                        flags = self.configuration["arguments"]
                        reminder = int(flags[flags.index("--context-reminder-tokens") + 1])
                        rollover = int(flags[flags.index("--context-rollover-tokens") + 1])
                        headroom = int(flags[flags.index("--context-response-headroom") + 1])
                        rollover = min(rollover, body["_observed_context"]["model"]["contextWindow"] - headroom)
                        assert reminder <= body["_base_meter"]["tokens"] < rollover, \
                            "Fresh-window tool output did not exercise the reminder interval"
                        assert reminders(body) == 1, "New window must receive exactly one capacity reminder"
                        self.checked("small_original_recovered_and_new_window_reminder")
                    else:
                        body, old_identity = yield from self.recover(self.anchor, self.evidence["old"])
                        assert reminders(body), "New window failed to reset reminder state"
                    if batch:
                        body, last_identity = yield from self.recover(self.evidence["before"].split("-")[-1], self.evidence["before"])
                        assert old_identity["window_id"] == last_identity["window_id"], "Automatic reset split the outgoing batch across windows"
                        self.checked("automatic_reset_finishes_batch_and_uses_last_note")
                    self.checked("automatic_rollover_and_per_window_reminder")
        self.done = True
        yield {"content": "VERIFIED-" + self.nonce}

    def script_reminder_boundary(self, body):
        record = self.saved["capacity_boundary"]
        arguments = self.configuration["arguments"]
        rollover = int(arguments[arguments.index("--context-rollover-tokens") + 1])
        reminder = int(arguments[arguments.index("--context-reminder-tokens") + 1])
        headroom = int(arguments[arguments.index("--context-response-headroom") + 1])
        body = yield calls(call("new_context"))
        self.check_fresh(body, notes=False)
        baseline = body["_base_meter"]["tokens"]
        notices = [message for message in body["_observed_context"]["messages"]
                   if message.get("role") == "custom" and message.get("customType") == "context_capacity_reminder"]
        if baseline >= reminder or notices:
            raise ScoringError("Reminder boundary fixture lacks an unreminded fresh baseline below its threshold")
        pending_tokens = base_estimate_message({"role": "user", "content": self.correction})
        assistant_tokens = rollover - 1 - baseline - pending_tokens
        prefix = self.current_marker + "\n"
        if assistant_tokens * 4 < utf16_length(prefix):
            raise ScoringError("Reminder boundary fixture cannot construct a positive normal old response")
        response = prefix + "A" * (assistant_tokens * 4 - utf16_length(prefix))
        record["baseline"] = {
            "actual_meter": baseline, "pending_tokens": pending_tokens, "assistant_tokens": assistant_tokens,
            "prediction_only": baseline + pending_tokens + assistant_tokens,
            "prediction_assumption": "effective setup unchanged; not an observation of the following request",
        }
        body = yield {"content": response}
        meter = body["_base_meter"]["tokens"]
        current_budget = body["_observed_context"]["model"]["contextWindow"] - headroom
        old_present = lossless_text_visible(body, self.current_marker)
        record.update(actual_required_request=len(self.requests), actual_meter=meter,
                      old_response_visible=old_present,
                      unpresented_input_visible=lossless_text_visible(body, self.correction))
        assert record["unpresented_input_visible"], "Unpresented user input lost at the reminder boundary"
        assert meter < current_budget, "Required request exceeds the current model input budget"
        if old_present:
            assert meter < min(rollover, current_budget), "Outgoing request reached rollover without resetting"
            notices = [message for message in body["_observed_context"]["messages"]
                       if message.get("role") == "custom" and message.get("customType") == "context_capacity_reminder"]
            assert len(notices) <= 1, "Reminder duplicated in the same window"
            notice_cost = sum(base_estimate_message(message) for message in notices)
            before_notice = meter - notice_cost
            assert len(notices) == int(before_notice >= reminder), "Reminder presence disagrees with actual input threshold"
            for notice in notices:
                encoded = text(notice)
                value = json.loads(encoded)
                assert type(value.get("remaining_tokens")) is int and value["remaining_tokens"] >= 0, "Reminder lacks remaining capacity"
                assert isinstance(value.get("message"), str) and value["message"].strip(), "Reminder lacks model guidance"
                assert encoded in all_text(body), "Reminder did not enter actual model input"
            record.update(coverage="not_exercised", branch="legal_request_without_rollover",
                          observed_reminder_tokens=notice_cost, actual_input_without_observed_reminders=before_notice)
        else:
            self.check_fresh(body, notes=False)
            record.update(coverage="fresh_request_observed", branch="fresh_required_request",
                          reset_trigger="not_inferred_from_fresh_request_alone")
        self.checked("required_pending_turn_at_reminder_boundary")
        self.done = True
        yield {"content": "VERIFIED-" + self.nonce}

    def respond(self, wire, observation=None):
        body=normalize(wire)
        context = observation["context"] if observation is not None else {"messages": []}
        body["_observed_context"] = context
        body["_base_meter"] = (
            base_observed_meter(context)
            if observation is not None and self.name in CAPACITY_CASES
            else None
        )
        body["_reminders"] = [text(message) for message in context["messages"]
                              if message.get("role") == "custom" and message.get("customType") == "context_capacity_reminder"]
        self.requests.append(body)
        pair_check(body)
        for event in self.events:
            if event.get("type") == "tool_execution_end" and event.get("toolName") in TOOLS and not event.get("isError"):
                content = event["result"].get("content", [])
                encoded = "".join(part["text"] for part in content if part.get("type") == "text")
                try:
                    json.loads(encoded)
                except (ValueError, TypeError):
                    raise AssertionError(f"Successful {event['toolName']} did not return JSON text")
        delta=self.script.send(body)
        self.emitted.extend(delta.get("tool_calls",[]))
        return delta


def model_usage(body, delta):
    # The scripted provider reports current-request usage, never lifetime usage.
    # Its synthetic usage uses four UTF-8 bytes per token; capacity assertions
    # independently use the statement's fixed Base estimateTokens semantics.
    model_input = {key: body[key] for key in ("messages", "tools", "instructions", "input") if key in body}
    measure = lambda value: max(1, (len(json.dumps(value, ensure_ascii=False).encode()) + 3) // 4)
    return {"input_tokens": measure(model_input), "output_tokens": measure(delta)}


def response_sse(delta, usage):
    ident="resp_"+uuid.uuid4().hex
    events=[{"type":"response.created","response":{"id":ident,"status":"in_progress","output":[]}}]
    output=[]
    if delta.get("content"):
        output.append({"type":"message","id":"msg_"+uuid.uuid4().hex,"role":"assistant","status":"completed",
                       "content":[{"type":"output_text","text":delta["content"],"annotations":[]}]})
    for c in delta.get("tool_calls",[]):
        output.append({"type":"function_call","id":"fc_"+uuid.uuid4().hex,"call_id":c["id"],"name":c["function"]["name"],"arguments":c["function"]["arguments"],"status":"completed"})
    for i,item in enumerate(output):
        empty=dict(item)
        if item["type"]=="function_call":empty["arguments"]=""
        else:empty["content"]=[]
        events.extend([{"type":"response.output_item.added","output_index":i,"item":empty},
                       {"type":"response.output_item.done","output_index":i,"item":item}])
    events.append({"type":"response.completed","response":{"id":ident,"status":"completed","model":"scripted","output":output,
                   "usage":dict(usage, total_tokens=usage["input_tokens"] + usage["output_tokens"])}})
    return "".join("event: "+e["type"]+"\ndata: "+json.dumps(e,ensure_ascii=False)+"\n\n" for e in events).encode()


def handler(scenario):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            try:
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                content_type="text/plain"
                if self.path=="/event":scenario.event_diagnostics.append(body);payload=b"ok"
                elif self.path=="/evidence":
                    scenario.served.append(body["key"])
                    if body["key"] == "hold":
                        scenario.hold_started.set()
                        assert scenario.hold_release.wait(30), "Held tool was not released after queued input"
                    payload=scenario.evidence[body["key"]].encode()
                elif self.path in ["/v1/chat/completions","/v1/responses"]:
                    api = "openai-responses" if self.path.endswith("responses") else "openai-completions"
                    # Preserve the original actual HTTP object for usage calculation.
                    usage_body = dict(body)
                    try:
                        observation = scenario.observer.consume_model_request(body, api)
                    except NoUnusedProviderObservation as exc:
                        if not claim_ordinary_compaction_request(scenario, exc, body):
                            raise
                        delta = {"content": "Ordinary compaction summary request observed by verifier."}
                    else:
                        scenario.events = scenario.previous_phase_events + public_events(scenario.observer.snapshot_events())
                        delta=scenario.respond(body, observation)
                    usage=model_usage(usage_body, delta)
                    content_type="text/event-stream"
                    if self.path.endswith("responses"):payload=response_sse(delta, usage)
                    else:
                        chunks=[{"id":"chatcmpl-local","object":"chat.completion.chunk","created":1,"model":"scripted",
                                 "choices":[{"index":0,"delta":d,"finish_reason":f}]} for d,f in [(dict(role="assistant",**delta),None),({},"tool_calls" if "tool_calls" in delta else "stop")]]
                        chunks[-1]["usage"] = {"prompt_tokens": usage["input_tokens"], "completion_tokens": usage["output_tokens"], "total_tokens": sum(usage.values())}
                        payload=("".join("data: "+json.dumps(c,ensure_ascii=False)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
                else:raise AssertionError("Unexpected endpoint: "+self.path)
                self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
            except Exception as exc:
                (scenario.scoring_errors if isinstance(exc, ScoringError) else scenario.errors).append(repr(exc))
                payload=json.dumps({"error":{"message":repr(exc),"type":"invalid_request_error"}}).encode()
                try:
                    self.send_response(400);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
                except OSError:pass
    return Handler


def classify_rpc_wait_errors(scenario):
    """Resolve derived RPC wait failures after observer/startup attribution.

    A missing held tool or acknowledgement is not independent evidence of a
    product violation when trusted startup/observation has already failed.
    Existing concrete product errors remain intact and retain their priority.
    """
    if not scenario.scoring_errors:
        scenario.errors.extend(scenario.rpc_wait_errors)
        if scenario.name in REMINDER_BOUNDARY_CASES:
            boundary = scenario.saved["capacity_boundary"]
            if boundary["pending_prompt_sent"] and (boundary["actual_required_request"] is None
                                                     or not scenario.done or not boundary["turn_settled"]):
                if "required_pending_turn_did_not_complete" not in scenario.errors:
                    scenario.errors.append("required_pending_turn_did_not_complete")


def is_visible_error_event(event):
    """Recognize supported public Pi error-reporting channels."""
    if event.get("type") == "extension_error" and event.get("error"):
        return True
    if event.get("type") == "extension_ui_request":
        return (event.get("method") == "notify" and event.get("notifyType") == "error"
                and isinstance(event.get("message"), str) and bool(event["message"].strip()))
    message = event.get("message", {})
    return (event.get("type") in ("message_end", "turn_end")
            and message.get("role") == "assistant" and message.get("stopReason") == "error"
            and isinstance(message.get("errorMessage"), str) and bool(message["errorMessage"].strip()))


def active_automatic_compaction(observations, session_id):
    """Return this session's trusted open non-manual compaction attempt, if any."""
    active = None
    for envelope in observations:
        fact = envelope["fact"]
        if fact.get("session_id") != session_id:
            continue
        kind = fact.get("kind")
        reason = fact.get("reason") if kind != "session_compact_failed" else fact.get("event", {}).get("reason")
        if kind == "compaction_attempt" and reason != "manual":
            active = envelope
        elif kind in ("session_compact", "session_compact_failed") and reason != "manual":
            active = None
    return active


def is_ordinary_compaction_result(event):
    return (event.get("type") == "session_compact" and event.get("reason") != "manual"
            and event.get("from_extension") is False)


def claim_ordinary_compaction_request(scenario, error, body):
    """Classify actual summary HTTP only during a trusted active automatic compaction."""
    if scenario.name != "capacity_compaction" or not isinstance(error, NoUnusedProviderObservation):
        return False
    facts = scenario.observer.snapshot_events()
    consumed = [event for event in facts if event["fact"].get("kind") == "provider_request"
                and event["observation_seq"] in scenario.observer.consumed_providers]
    if not consumed:
        return False
    attempt = active_automatic_compaction(facts, consumed[-1]["fact"].get("session_id"))
    if attempt is None:
        return False
    scenario.ordinary_compaction_requests.append({"attempt": attempt, "request": body})
    scenario.errors.append("Ordinary compaction sent a separate provider summary request")
    return True


def exit_codes_acceptable(name, exits):
    """Invalid public configuration may terminate normally with a nonzero code."""
    if name in INVALID_FLAG_CASES:
        return all(isinstance(code, int) and code >= 0 for code in exits)
    return all(code == 0 for code in exits)


def communicate_pending_input(proc, scenario):
    """Send actual RPC user input while a real tool awaits its external result."""
    stdout, stderr = [], []
    queued, ended = threading.Event(), threading.Event()

    def read_stdout():
        for line in proc.stdout:
            stdout.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "response" and event.get("id") == "pending-user":
                if event.get("success"):
                    queued.set()
                else:
                    scenario.errors.append("RPC rejected the pending user input")
            if event.get("type") == "agent_end" and scenario.done:
                ended.set()

    readers = [threading.Thread(target=read_stdout, daemon=True),
               threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True)]
    for reader in readers:
        reader.start()

    def send(command):
        proc.stdin.write(json.dumps(command) + "\n")
        proc.stdin.flush()

    try:
        send({"id": "initial-user", "type": "prompt", "message": scenario.goal})
        assert scenario.hold_started.wait(30), "Scenario never reached the held external tool"
        send({"id": "pending-user", "type": "steer", "message": scenario.correction})
        assert queued.wait(30), "Pi did not acknowledge queued user input"
        # The acknowledgement follows session.steer(), so the tool can only
        # finish after the new input is truly queued, without a timing sleep.
        scenario.hold_release.set()
        assert ended.wait(30), "Pending-input scenario did not complete"
        proc.stdin.close()
        proc.wait(timeout=10)
    except (AssertionError, BrokenPipeError, subprocess.TimeoutExpired) as exc:
        scenario.rpc_wait_errors.append(str(exc))
        scenario.hold_release.set()
        if proc.poll() is None:
            scenario.observer.mark_cancelled()
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    finally:
        for reader in readers:
            reader.join(timeout=5)
    return "".join(stdout), "".join(stderr)


def communicate_idle_input(proc, scenario):
    """Finish one turn, prove idle, then prompt again through the same RPC PID."""
    stdout, stderr = [], []
    first_end, state_reply, final_end = threading.Event(), threading.Event(), threading.Event()
    state = {}

    def read_stdout():
        for line in proc.stdout:
            stdout.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "agent_end":
                (final_end if scenario.done else first_end).set()
            if event.get("type") == "response" and event.get("id") == "idle-state":
                state.update(event)
                state_reply.set()

    readers = [threading.Thread(target=read_stdout, daemon=True),
               threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True)]
    for reader in readers:
        reader.start()

    def send(command):
        proc.stdin.write(json.dumps(command) + "\n")
        proc.stdin.flush()

    try:
        send({"id": "initial-user", "type": "prompt", "message": scenario.goal})
        assert first_end.wait(30), "Initial RPC turn did not reach idle"
        requests_at_idle = len(scenario.requests)
        send({"id": "idle-state", "type": "get_state"})
        assert state_reply.wait(30), "RPC did not answer get_state while idle"
        assert state.get("success") and not state.get("data", {}).get("isStreaming"), "RPC process was not idle"
        assert len(scenario.requests) == requests_at_idle, "Idle state check started an extra model request"
        send({"id": "second-user", "type": "prompt", "message": scenario.correction})
        assert final_end.wait(30), "Same-process post-idle prompt did not complete"
        proc.stdin.close()
        proc.wait(timeout=10)
    except (AssertionError, BrokenPipeError, subprocess.TimeoutExpired) as exc:
        scenario.rpc_wait_errors.append(str(exc))
        if proc.poll() is None:
            scenario.observer.mark_cancelled()
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    finally:
        for reader in readers:
            reader.join(timeout=5)
    return "".join(stdout), "".join(stderr)


def communicate_reminder_boundary(proc, scenario):
    """Observe completion or abort of one required post-idle public prompt."""
    stdout, stderr = [], []
    first_end, state_reply, second_end, second_sent = (threading.Event() for _ in range(4))
    state = {}
    record = scenario.saved["capacity_boundary"]

    def read_stdout():
        for line in proc.stdout:
            stdout.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "agent_end":
                (second_end if second_sent.is_set() else first_end).set()
            elif event.get("type") == "response" and event.get("id") == "boundary-idle":
                state.update(event)
                state_reply.set()
            if is_visible_error_event(event):
                record["visible_errors"].append(event)

    def read_stream(reader):
        try:
            reader()
        except (OSError, UnicodeError) as exc:
            scenario.scoring_errors.append("RPC driver could not read process output: " + str(exc))
            # Release driver waits so a broken observation channel is not
            # subsequently reported as a candidate failing to make progress.
            for ready in (first_end, state_reply, second_end):
                ready.set()

    readers = [threading.Thread(target=read_stream, args=(read_stdout,), daemon=True),
               threading.Thread(target=read_stream, args=(lambda: stderr.extend(proc.stderr),), daemon=True)]
    for reader in readers:
        reader.start()

    def send(command):
        proc.stdin.write(json.dumps(command) + "\n")
        proc.stdin.flush()

    try:
        send({"id": "boundary-initial", "type": "prompt", "message": scenario.goal})
        assert first_end.wait(30), "Initial RPC turn did not reach idle"
        if "baseline" not in record:
            if not scenario.errors and not scenario.scoring_errors:
                # A candidate may abort the required prompt before any HTTP.
                # Attribute this derived failure only after observer.finish(),
                # so a real observation/startup fault still remains unscored.
                raise AssertionError("Initial required prompt did not reach the provider")
        else:
            count = len(scenario.requests)
            send({"id": "boundary-idle", "type": "get_state"})
            if not state_reply.wait(30) or not state.get("success"):
                raise ScoringError("RPC driver could not establish public idle state")
            if not isinstance(state.get("data"), dict) or type(state["data"].get("isStreaming")) is not bool:
                raise ScoringError("RPC driver received an invalid public idle-state reply")
            record["idle"] = {"response": state, "requests_before": count,
                              "requests_after": len(scenario.requests)}
            assert not state.get("data", {}).get("isStreaming"), "RPC process was not idle"
            assert len(scenario.requests) == count, "Idle capacity check started an extra model request"
            second_sent.set()
            send({"id": "boundary-pending", "type": "prompt", "message": scenario.correction})
            record["pending_prompt_sent"] = True
            assert second_end.wait(30), "required_pending_turn_did_not_complete"
            record["turn_settled"] = True
        proc.stdin.close()
        proc.wait(timeout=10)
    except (AssertionError, OSError, subprocess.TimeoutExpired, ScoringError) as exc:
        if isinstance(exc, (OSError, ScoringError)):
            scenario.scoring_errors.append("RPC driver: " + str(exc))
        else:
            scenario.rpc_wait_errors.append(str(exc))
        if proc.poll() is None:
            scenario.observer.mark_cancelled()
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    finally:
        for reader in readers:
            reader.join(timeout=5)
    return "".join(stdout), "".join(stderr)


def communicate_oversized_recovery(proc, scenario):
    """Observe an oversize error, switch model publicly, and recover in one PID."""
    stdout, stderr = [], []
    first_end, visible_error, error_end = threading.Event(), threading.Event(), threading.Event()
    model_reply, final_end = threading.Event(), threading.Event()
    model_response, visible_errors = {}, []

    def read_stdout():
        for line in proc.stdout:
            stdout.append(line)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if is_visible_error_event(event):
                visible_errors.append(event)
                visible_error.set()
            elif event.get("type") == "agent_end":
                if scenario.done:
                    final_end.set()
                elif visible_error.is_set():
                    error_end.set()
                else:
                    first_end.set()
            elif event.get("type") == "response" and event.get("id") == "model-switch":
                model_response.update(event)
                model_reply.set()

    readers = [threading.Thread(target=read_stdout, daemon=True),
               threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True)]
    for reader in readers:
        reader.start()

    def send(command):
        proc.stdin.write(json.dumps(command) + "\n")
        proc.stdin.flush()

    try:
        send({"id": "initial-user", "type": "prompt", "message": scenario.goal})
        if scenario.name == "capacity_oversized_input":
            assert first_end.wait(30), "Initial RPC turn did not finish before oversized input"
            send({"id": "oversized-user", "type": "prompt", "message": scenario.correction})
        assert visible_error.wait(30), "Irreducible fresh context did not report a visible extension error"
        assert error_end.wait(30), "Oversized turn did not return to idle"
        assert len(scenario.requests) == 1, "Oversized model request escaped before recovery"
        scenario.saved["visible_errors"] = visible_errors
        send({"id": "model-switch", "type": "set_model", "provider": "context-test", "modelId": "scripted-large"})
        assert model_reply.wait(30), "Public set_model did not respond"
        assert model_response.get("success") and model_response.get("data", {}).get("id") == "scripted-large", "Public set_model failed"
        scenario.saved["recovery_prompt"] = "recovery-after-visible-error-" + uuid.uuid4().hex
        send({"id": "recovery-user", "type": "prompt", "message": scenario.saved["recovery_prompt"]})
        assert final_end.wait(30), "Same-process recovery prompt did not complete"
        assert len(scenario.requests) >= 2, "Larger public model did not receive the recovered request"
        proc.stdin.close()
        proc.wait(timeout=10)
    except (AssertionError, BrokenPipeError, subprocess.TimeoutExpired) as exc:
        scenario.rpc_wait_errors.append(str(exc))
        if proc.poll() is None:
            scenario.observer.mark_cancelled()
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    finally:
        for reader in readers:
            reader.join(timeout=5)
    return "".join(stdout), "".join(stderr)


def run_case(name, repo, output):
    directory = output / name
    directory.mkdir(parents=True)
    for child in ["agent", "home", "tmp", "workspace", "state"]: (directory / child).mkdir()
    credentials = {}
    if os.geteuid() == 0:
        account = pwd.getpwnam("agent")
        credentials = {"user": account.pw_uid, "group": account.pw_gid, "extra_groups": []}
        # Candidate-writable state is separate from trusted reports and scorer.
        for parent in [output.parent, output, directory]: parent.chmod(0o755)
        for child in ["agent", "home", "tmp", "workspace", "state"]:
            os.chown(directory / child, account.pw_uid, account.pw_gid)
            (directory / child).chmod(0o700)
    scenario = Scenario(name)
    # Trusted startup defects must be attributed before any candidate is run.
    preflight = RuntimeObserver(directory, repo)
    preflight.preflight()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(scenario))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (directory / "workspace/keep.txt").write_text(scenario.nonce)
    (directory / "agent/settings.json").write_text(json.dumps({"compaction": {"enabled": False}, "retry": {"enabled": False}}))
    env = {
        "PATH": os.environ["PATH"], "LANG": "C.UTF-8", "HOME": str(directory / "home"), "TMPDIR": str(directory / "tmp"),
        "PI_CODING_AGENT_DIR": str(directory / "agent"), "PI_CONTEXT_TEST_URL": f"http://127.0.0.1:{server.server_port}",
        "NODE_OPTIONS": f"--import={Path(__file__).with_name('context_observation.mjs').resolve()} --import={repo}/node_modules/tsx/dist/loader.mjs", "TSX_TSCONFIG_PATH": str(repo / "tsconfig.json"),
        "PI_CONTEXT_TEST_REASONING": "1" if name in ["thinking_search", "thinking_read"] else "0",
        "PI_CONTEXT_TEST_API": "openai-responses" if name == "responses" else "openai-completions",
        "PI_NO_LOCAL_LLM": "1", "AWS_EC2_METADATA_DISABLED": "true", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    if credentials:
        for file in [directory / "workspace/keep.txt", directory / "agent/settings.json"]:
            os.chown(file, credentials["user"], credentials["group"])
            file.chmod(0o600)
    configuration = scenario.configuration
    env.update(configuration.get("environment", {}))
    for key, value in configuration.get("provider", {}).items():
        assert key in ("context_window", "max_tokens", "large_context_window", "large_max_tokens"), "Unknown reviewed provider parameter"
        env["PI_CONTEXT_TEST_" + key.upper()] = str(value)
    for relative, content in configuration.get("files", {}).items():
        path = Path(relative)
        assert not path.is_absolute() and ".." not in path.parts and path.parts[0] in ("agent", "home", "workspace"), "Unsafe reviewed configuration path"
        target = directory / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if credentials:
            for parent in [target, *target.parents]:
                if parent == directory:
                    break
                os.chown(parent, credentials["user"], credentials["group"])
    phases = 2 if name in ["resume", "isolation", "clear_resume", "history_all", "capacity_idle"] else 1
    exits = []
    try:
        for phase in range(phases):
            scenario.done = False
            scenario.script = scenario.script_main(phase)
            next(scenario.script)
            session = directory / "state" / ("other.jsonl" if name == "isolation" and phase else "session.jsonl")
            rpc = name in ("pending_input", "capacity_pending", "capacity_idle_rpc", "capacity_oversized_notes", "capacity_oversized_input", *REMINDER_BOUNDARY_CASES)
            command = ["node", "--inspect-brk=127.0.0.1:0", str(repo / "packages/coding-agent/src/cli.ts"), "--mode", "rpc" if rpc else "json", "--session", str(session),
                       "--model", "context-test/scripted", "--system-prompt", scenario.system,
                       ]
            extension = repo / "packages/coding-agent/examples/extensions/context-management/index.ts"
            # Baseline starts normally and is scored for absent advertised tools,
            # not for failure to import a file which the task asks solvers to add.
            if name != "ordinary" and extension.exists(): command += ["-e", str(extension)]
            command += ["-e", str(Path(__file__).with_name("provider.ts"))]
            for argument in configuration.get("arguments", []) if extension.exists() and name != "ordinary" else []:
                for child in ("agent", "home", "workspace"):
                    argument = argument.replace("{" + child + "}", str(directory / child))
                command.append(argument)
            if not rpc:
                command += ["-p", scenario.goal if phase == 0 else scenario.correction]
            scenario.previous_phase_events = list(scenario.events)
            observer = scenario.observer = RuntimeObserver(directory, repo)
            observer.preflight()
            (directory / f"command-{phase}.json").write_text(json.dumps({"command": command, "environment": env, "input_sha256": observer.hashes}, indent=2))
            proc = subprocess.Popen(command, cwd=directory / "workspace", env=env, stdin=subprocess.PIPE if rpc else None,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, **credentials)
            observer.attach(proc.pid, phase)
            cancelled = False
            try:
                if name in ("pending_input", "capacity_pending"):
                    stdout, stderr = communicate_pending_input(proc, scenario)
                elif name == "capacity_idle_rpc":
                    stdout, stderr = communicate_idle_input(proc, scenario)
                elif name in REMINDER_BOUNDARY_CASES:
                    stdout, stderr = communicate_reminder_boundary(proc, scenario)
                elif name in ("capacity_oversized_notes", "capacity_oversized_input"):
                    stdout, stderr = communicate_oversized_recovery(proc, scenario)
                else:
                    stdout, stderr = proc.communicate(timeout=RUN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                cancelled = True
                observer.mark_cancelled()
                if observer.errors:
                    scenario.scoring_errors.extend(observer.errors)
                else:
                    scenario.errors.append("Pi did not complete the scenario")
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
            report = observer.finish(scenario.done, cancelled)
            scenario.observer_reports.append({key: value for key, value in report.items() if key != "native_coverage"})
            scenario.events = scenario.previous_phase_events + public_events(observer.snapshot_events())
            scenario.scoring_errors.extend(report["errors"])
            if name == "capacity_compaction" and any(is_ordinary_compaction_result(event)
                                                       for event in scenario.events):
                scenario.errors.append("Ordinary automatic compaction produced a summary result")
            exits.append(proc.returncode)
            (directory / f"stdout-{phase}.jsonl").write_text(stdout)
            (directory / f"stderr-{phase}.txt").write_text(stderr)
            if not report["fixture_ready"]:
                # An observed explicit process.exit during candidate loading is
                # a product early exit. Missing ready alone is not that proof.
                exits_observed = [e for e in observer.snapshot_events() if e["fact"]["kind"] == "process_exit"]
                explicit_exit = any(any(f["function"] == "exit" and f["url"].startswith("node:") for f in e.get("stack", [])) for e in exits_observed)
                candidate_frame = any(any(str(extension) in f["url"] or "/jiti/" in f["url"] or "/jiti-" in f["url"] for f in e.get("stack", [])) for e in exits_observed)
                if report["boot"] and explicit_exit and candidate_frame and not report["errors"]:
                    scenario.errors.append("Candidate explicitly exited while loading before fixture readiness")
                else:
                    scenario.scoring_errors.append("Trusted fixture did not become ready; startup attribution incomplete")
            classify_rpc_wait_errors(scenario)
            if name in INVALID_FLAG_CASES:
                visible = []
                for line in stdout.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("type") == "extension_error" and event.get("error"):
                        visible.append(event)
                    message = event.get("message", {})
                    if event.get("type") in ("message_end", "turn_end") and message.get("role") == "assistant" \
                            and message.get("stopReason") == "error" and message.get("errorMessage"):
                        visible.append(event)
                debugger_lines = ("Debugger listening on ", "For help, see:", "Debugger attached.",
                                  "Waiting for the debugger to disconnect...")
                stderr_errors = [line for line in stderr.splitlines()
                                 if line.strip() and not line.startswith(debugger_lines)]
                if stderr_errors:
                    visible.append({"type": "stderr_error", "lines": len(stderr_errors)})
                if scenario.requests:
                    scenario.errors.append("Invalid public flags reached an HTTP model request")
                elif not visible:
                    scenario.errors.append("Invalid public flags produced no visible extension error")
                else:
                    scenario.saved["visible_errors"] = visible
                    scenario.done = True
                    scenario.checked("invalid_public_flags_are_visibly_rejected_before_http")
            if (not scenario.done or "VERIFIED-" + scenario.nonce not in stdout) and name not in INVALID_FLAG_CASES:
                if not scenario.scoring_errors:
                    pending_boundary = name in REMINDER_BOUNDARY_CASES and scenario.saved["capacity_boundary"]["pending_prompt_sent"]
                    reason = "required_pending_turn_did_not_complete" if pending_boundary else "Required scripted trajectory did not complete"
                    if reason not in scenario.errors:
                        scenario.errors.append(reason)
            if proc.returncode or scenario.errors or scenario.scoring_errors: break
        if name in INVALID_FLAG_CASES and not exit_codes_acceptable(name, exits):
            scenario.errors.append("Invalid public flag rejection terminated abnormally")
        if scenario.scoring_errors or scenario.errors:
            raise ScoringError("; ".join(scenario.scoring_errors)) if scenario.scoring_errors and not scenario.errors else AssertionError("Candidate checks failed")
        sessions = [e["id"] for e in scenario.events if e.get("type") == "session"]
        if name not in INVALID_FLAG_CASES:
            assert len(sessions) == len(exits), "Context reset created or replaced a session"
            request_sessions = {e["id"] for e in scenario.events if e.get("type") == "request_session"}
            assert request_sessions == set(sessions), "Model calls changed session identity"
        if name in ["resume", "clear_resume", "history_all", "capacity_idle"] and len(sessions) == 2:
            assert sessions[0] == sessions[1], "Resume changed session identity"
        if name == "isolation" and len(sessions) == 2:
            assert sessions[0] != sessions[1], "Independent sessions share identity"
        assert (directory / "workspace/keep.txt").read_text() == scenario.nonce, "Context transition reset workspace"
        if name == "ordinary" and scenario.done:
            assert (directory / "workspace/builtin-output.txt").read_text() == "builtin-bash-" + scenario.nonce, "Builtin Bash filesystem effect missing while extension disabled"
            scenario.checked("disabled_builtin_bash_filesystem_effect")
        passed = (not scenario.errors and not scenario.scoring_errors and len(exits) == phases
                  and exit_codes_acceptable(name, exits))
    except Exception as exc:
        (scenario.scoring_errors if isinstance(exc, ScoringError) else scenario.errors).append(repr(exc))
        passed = False
    finally:
        server.shutdown()
        server.server_close()
    for filename, data in [("requests", scenario.requests), ("events", scenario.events), ("event-diagnostics", scenario.event_diagnostics)]:
        (directory / (filename + ".json")).write_text(json.dumps(data, ensure_ascii=True, indent=2))
    if scenario.ordinary_compaction_requests:
        (directory / "ordinary-compaction-requests.json").write_text(
            json.dumps(scenario.ordinary_compaction_requests, ensure_ascii=True, indent=2))
    status = "pass" if passed else "candidate_failure" if scenario.errors else "scoring_error"
    result_data = {"name": name, "passed": passed, "status": status, "errors": scenario.errors,
                   "scoring_errors": scenario.scoring_errors, "rpc_wait_errors": scenario.rpc_wait_errors,
                   "exits": exits, "requests": len(scenario.requests),
                   "ordinary_compaction_requests": len(scenario.ordinary_compaction_requests),
                   "checks": scenario.checks, "observers": scenario.observer_reports}
    if name in REMINDER_BOUNDARY_CASES:
        result_data["capacity_boundary"] = scenario.saved["capacity_boundary"]
    (directory / "result.json").write_text(json.dumps(result_data, ensure_ascii=True, indent=2))
    return result_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/workspace/pi"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier/behavior"))
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    inputs = {name: Path(__file__).with_name(name) for name in ("verify.py", "provider.ts", "runtime_observer.py", "context_observation.mjs")}
    def identities():
        return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}
    input_hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for name, path in inputs.items()}
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.cases:
        try: data = run_case(name, args.repo.resolve(), args.output)
        except Exception as exc: data = {"name": name, "passed": False, "status": "scoring_error", "errors": [], "scoring_errors": [repr(exc)]}
        results.append(data)
        print(json.dumps(data, ensure_ascii=True), flush=True)
    unchanged = all(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == input_hashes[name] for name, path in inputs.items())
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results), "external_model_calls": 0,
               "input_sha256": input_hashes, "inputs_unchanged": unchanged, "results": results}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2))
    status = "scoring_error" if not unchanged or any(r["status"] == "scoring_error" for r in results) else "scored" if all(r["passed"] for r in results) else "candidate_failure"
    (args.output / "grading-status.json").write_text(json.dumps({"status": status, "scenario_inventory": args.cases,
        "completed_scenarios": [r["name"] for r in results], "input_sha256": input_hashes, "inputs_unchanged": unchanged}, indent=2))
    return 2 if status == "scoring_error" else 0 if status == "scored" else 1


if __name__ == "__main__": raise SystemExit(main())
