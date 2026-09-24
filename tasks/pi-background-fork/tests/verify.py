#!/usr/bin/python3
"""Behavioral verifier for the pi fork extension.

Every case runs a real pi parent process in RPC mode as the unprivileged `node` user,
with the candidate extension and a verifier fixture installed through the agent
directory's settings.json. Both talk to a scripted OpenAI-compatible endpoint served
here, so every provider request of the parent and of each fork is recorded exactly as
pi sent it. Forks are whatever processes the candidate starts; the verifier only
observes them (requests, lifecycle events, /proc) and never imports candidate code.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("PI_WORKSPACE", "/workspace/pi"))
CLI = REPO / "packages/coding-agent/dist/cli.js"
EXTENSION = REPO / "packages/coding-agent/examples/extensions/fork/index.ts"
NODE = "/usr/local/bin/node"
SUMMARY_PROMPT = "You are a context summarization assistant"
SYNTHETIC_RESULT = "No result provided"
STOP_BOUND = 5.0  # seconds within which a session's forks must be gone
WAIT = 45.0

CASES = [
    "basic_fork",
    "deliver_while_running",
    "compacted_context",
    "parallel_forks",
    "failed_forks",
    "quit_stops_forks",
    "switch_stops_forks",
    "reload_keeps_forks",
    "empty_task",
    "final_answer",
    "parent_killed",
    "deliver_at_run_end",
    "fork_beside_running_tool",
    "deliver_during_compaction",
    "finish_during_reload",
    "interrupted_delivery",
]


class Fail(AssertionError):
    pass


def check(condition, message):
    if not condition:
        raise Fail(message)


# ---------------------------------------------------------------- request views

def content_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "\n".join(parts)


def norm(message):
    """Comparable view of one chat-completions message (ids and formatting ignored)."""
    calls = [
        (call.get("function", {}).get("name"), json.loads(call.get("function", {}).get("arguments") or "{}"))
        for call in message.get("tool_calls") or []
    ]
    return {"role": message.get("role"), "text": content_text(message.get("content")), "calls": calls}


def convo(body):
    return [m for m in body.get("messages", []) if m.get("role") not in ("system", "developer")]


def all_text(body):
    chunks = []
    for m in body.get("messages", []):
        chunks.append(content_text(m.get("content")))
        for call in m.get("tool_calls") or []:
            chunks.append(call.get("function", {}).get("arguments") or "")
    return "\n".join(chunks)


def tool_names(body):
    return sorted(t.get("function", {}).get("name") for t in body.get("tools") or [])


def is_summary(body):
    return any(m.get("role") in ("system", "developer") and content_text(m.get("content")).startswith(SUMMARY_PROMPT)
               for m in body.get("messages", []))


# ---------------------------------------------------------------- case runtime

class Case:
    def __init__(self, name):
        self.name = name
        self.lock = threading.Condition()
        self.requests = []  # {"pid", "t", "body", "index"}
        self.events = []    # {"pid", "t", "event", ...}
        self.gates = {}     # name -> threading.Event
        self.errors = []
        self.parent_pid = None
        self.script = None  # callable(case, body, pid) -> response
        self.closed = False
        self.cmdlines = {}  # pid -> argv captured at the process's first model request
        self.exit_pids = set()
        self.summary_hook = None
        self.event_hook = None  # optional callable run before answering a fixture event  # optional callable run before answering a summary request  # fork pids told to exit abnormally after their next turn

    # --- synchronisation helpers
    def gate(self, name):
        with self.lock:
            return self.gates.setdefault(name, threading.Event())

    def record(self, kind, item):
        with self.lock:
            (self.requests if kind == "request" else self.events).append(item)
            self.lock.notify_all()

    def wait_until(self, predicate, what, timeout=WAIT):
        deadline = time.monotonic() + timeout
        with self.lock:
            while True:
                value = predicate()
                if value:
                    return value
                left = deadline - time.monotonic()
                if left <= 0:
                    raise Fail(f"timed out waiting for {what}")
                self.lock.wait(min(left, 0.2))

    def parent_requests(self):
        return [r for r in self.requests if r["pid"] == self.parent_pid and not is_summary(r["body"])]

    def child_requests(self):
        return [r for r in self.requests if r["pid"] != self.parent_pid and not is_summary(r["body"])]

    def child_pids(self):
        seen = []
        for r in self.requests:
            if r["pid"] != self.parent_pid and r["pid"] not in seen:
                seen.append(r["pid"])
        for e in self.events:
            if e["pid"] != self.parent_pid and e["pid"] not in seen:
                seen.append(e["pid"])
        return seen

    def requesting_children(self):
        seen = []
        for r in self.requests:
            if r["pid"] != self.parent_pid and r["pid"] not in seen:
                seen.append(r["pid"])
        return seen

    def first_request_of(self, pid):
        for r in self.requests:
            if r["pid"] == pid and not is_summary(r["body"]):
                return r
        return None

    def parent_events(self, name):
        return [e for e in self.events if e["pid"] == self.parent_pid and e["event"] == name]


def make_handler(case):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, payload, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/event":
                    item = {k: v for k, v in body.items()}
                    item["t"] = time.monotonic()
                    case.record("event", item)
                    if case.event_hook:
                        case.event_hook(case, item)
                    answer = b"exit" if item.get("event") == "turn_end" and item.get("pid") in case.exit_pids else b"ok"
                    return self.reply(200, answer, "text/plain")
                if self.path == "/hold":
                    released = case.gate("hold:" + str(body.get("key"))).wait(WAIT)
                    return self.reply(200, b"released" if released else b"timeout", "text/plain")
                if self.path != "/v1/chat/completions":
                    raise Fail("unexpected endpoint " + self.path)
                pid = int(self.headers["X-Pi-Test-Pid"])
                item = {"pid": pid, "t": time.monotonic(), "body": body}
                with case.lock:
                    if pid not in case.cmdlines:
                        case.cmdlines[pid] = [a.decode(errors="replace") for a in cmdline(pid) if a]
                case.record("request", item)
                if is_summary(body):
                    if case.summary_hook:
                        case.summary_hook(case, body, pid)
                    response = ("text", f"{case.name.upper()}-SUMMARY of the earlier conversation")
                else:
                    response = case.script(case, body, pid)
                if response[0] == "error":
                    payload = json.dumps({"error": {"message": response[1], "type": "server_error"}}).encode()
                    return self.reply(500, payload, "application/json")
                delta = {"role": "assistant"}
                if response[0] == "text":
                    delta["content"] = response[1]
                    finish = "stop"
                else:
                    delta["tool_calls"] = [
                        {"index": i, "id": "call_" + uuid.uuid4().hex[:12], "type": "function",
                         "function": {"name": name, "arguments": json.dumps(args)}}
                        for i, (name, args) in enumerate(response[1])
                    ]
                    finish = "tool_calls"
                cid = "chatcmpl-" + uuid.uuid4().hex
                chunks = [
                    {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model"),
                     "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": body.get("model"),
                     "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
                ]
                payload = ("".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n").encode()
                return self.reply(200, payload, "text/event-stream")
            except Exception as exc:  # keep every scripted failure visible
                if not case.closed and not isinstance(exc, (BrokenPipeError, ConnectionResetError)):
                    case.errors.append(f"endpoint: {exc}")
                try:
                    self.reply(400, json.dumps({"error": {"message": str(exc)}}).encode(), "application/json")
                except OSError:
                    pass
    return Handler


class Parent:
    """A pi process in RPC mode, driven over stdin/stdout JSON lines."""

    def __init__(self, case, env, cwd, args):
        self.case = case
        self.lines = []
        self.cond = threading.Condition()
        command = ["/usr/bin/python3", "-I", str(HERE / "run_as_node.py"), NODE, str(CLI), "--mode", "rpc", *args]
        self.proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, start_new_session=True)
        case.parent_pid = self.proc.pid
        self.stderr = []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=lambda: self.stderr.extend(self.proc.stderr), daemon=True).start()
        self.counter = 0

    def _read(self):
        for line in self.proc.stdout:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            with self.cond:
                self.lines.append(item)
                self.cond.notify_all()

    def send_nowait(self, command):
        self.counter += 1
        request_id = f"v{self.counter}"
        self.proc.stdin.write(json.dumps({"id": request_id, **command}) + "\n")
        self.proc.stdin.flush()
        return request_id

    def wait_response(self, request_id, what, timeout=WAIT):
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for item in self.lines:
                    if item.get("type") == "response" and item.get("id") == request_id:
                        return item
                left = deadline - time.monotonic()
                check(left > 0, f"RPC {what} got no response")
                self.cond.wait(min(left, 0.2))

    def send(self, command, timeout=WAIT):
        self.counter += 1
        request_id = f"v{self.counter}"
        self.proc.stdin.write(json.dumps({"id": request_id, **command}) + "\n")
        self.proc.stdin.flush()
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for item in self.lines:
                    if item.get("type") == "response" and item.get("id") == request_id:
                        check(item.get("success") is not False, f"RPC {command['type']} failed: {item.get('error')}")
                        return item
                left = deadline - time.monotonic()
                check(left > 0, f"RPC {command['type']} got no response")
                self.cond.wait(min(left, 0.2))

    def events(self, kind):
        with self.cond:
            return [item for item in self.lines if item.get("type") == kind]

    def wait_idle_runs(self, count, timeout=WAIT):
        """Wait until `count` agent_end events have been emitted and the agent is idle."""
        deadline = time.monotonic() + timeout
        with self.cond:
            while len([i for i in self.lines if i.get("type") == "agent_end"]) < count:
                left = deadline - time.monotonic()
                check(left > 0, f"parent did not finish run #{count}")
                self.cond.wait(min(left, 0.2))

    def prompt(self, text):
        return self.send({"type": "prompt", "message": text})

    def tool_ends(self, name):
        return [i for i in self.events("tool_execution_end") if i.get("toolName") == name]


def alive(pid):
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()[0]
        return state != "Z"
    except (FileNotFoundError, IndexError):
        return False


def cmdline(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except FileNotFoundError:
        return []


def kill_as_node(pid):
    subprocess.run(["/usr/bin/python3", "-I", str(HERE / "run_as_node.py"), "--kill", str(pid)],
                   env={"PATH": "/usr/bin:/bin"}, check=False)


def read_session(path):
    entries = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue  # a line still being appended
    return entries


def fork_results(path):
    if not Path(path).exists():
        return []  # pi creates the session file with the first assistant message
    return [e for e in read_session(path) if e.get("type") == "custom_message" and e.get("customType") == "fork-result"]


def entry_text(entry):
    return content_text(entry.get("content"))


# ---------------------------------------------------------------- shared assertions

def forking_request(case, marker):
    """The parent request whose response was the fork call (identified by its last user text)."""
    for r in case.parent_requests():
        msgs = convo(r["body"])
        if msgs and msgs[-1].get("role") == "user" and marker in content_text(msgs[-1].get("content")):
            return r
    raise Fail(f"no parent request ends with {marker}")


def check_inherited(case, child_pid, parent_request, own_task, other_tasks=()):
    """The fork's first request starts with the parent's context at the fork, then the
    forking assistant message; later messages answer every call and give the task."""
    first = case.first_request_of(child_pid)
    check(first is not None, f"fork {child_pid} sent no model request")
    parent_msgs = [norm(m) for m in convo(parent_request["body"])]
    child_msgs = [norm(m) for m in convo(first["body"])]
    check(len(child_msgs) > len(parent_msgs), "fork context is shorter than the parent's context at the fork")
    check(child_msgs[: len(parent_msgs)] == parent_msgs,
          "fork context does not start with the parent's context at the fork, in order")
    forking = child_msgs[len(parent_msgs)]
    check(forking["role"] == "assistant" and any(name == "fork" for name, _ in forking["calls"]),
          "the message after the parent's context is not the forking assistant message")
    raw_child = convo(first["body"])
    raw_forking = raw_child[len(parent_msgs)]
    call_ids = [c.get("id") for c in raw_forking.get("tool_calls") or []]
    rest = raw_child[len(parent_msgs) + 1:]
    answered = {m.get("tool_call_id"): content_text(m.get("content")) for m in rest if m.get("role") == "tool"}
    for call_id in call_ids:
        check(call_id in answered, "a tool call of the forking message is unanswered in the fork's context")
        check(answered[call_id].strip() != SYNTHETIC_RESULT,
              "a tool call of the forking message reached the fork without a result (provider placeholder)")
    later = "\n".join(content_text(m.get("content")) for m in rest)
    check(own_task in later, "the fork's task does not follow the forking message in the fork's context")
    # Sibling calls may be answered with anything (even their own tasks); what this fork is
    # told to do comes from user messages and from the answer to its own call.
    own_call = [c.get("id") for c in raw_forking.get("tool_calls") or []
                if own_task in (c.get("function", {}).get("arguments") or "")]
    told = "\n".join(content_text(m.get("content")) for m in rest
                     if m.get("role") == "user" or (m.get("role") == "tool" and m.get("tool_call_id") in own_call))
    check(own_task in told, "the fork's task does not follow the forking message in the fork's context")
    for other in other_tasks:
        check(other not in told, "another fork's task is given to this fork")
    return first


def check_never_sees(case, child_pid, markers):
    for r in case.requests:
        if r["pid"] != child_pid:
            continue
        text = all_text(r["body"])
        for marker in markers:
            check(marker not in text, f"the fork saw parent activity after the fork ({marker})")


def check_fork_tool_result(parent, index=None):
    ends = parent.tool_ends("fork")
    check(ends, "no fork tool result")
    ids = []
    for item in ends if index is None else [ends[index]]:
        check(not item.get("isError"), "fork tool returned an error: " + content_text(item.get("result", {}).get("content")))
        details = item.get("result", {}).get("details") or {}
        fork_id = details.get("forkId")
        check(isinstance(fork_id, str) and fork_id.strip(), "fork tool result details.forkId is missing")
        check(fork_id in content_text(item.get("result", {}).get("content")), "fork tool result text does not name the fork id")
        ids.append(fork_id)
    return ids


def check_result_entry(entry, fork_id, status, parent_file):
    details = entry.get("details") or {}
    check(entry.get("display") is True, "fork-result message is not displayed")
    check(details.get("forkId") == fork_id, "fork-result forkId does not match the tool result")
    check(details.get("status") == status, f"fork-result status is {details.get('status')!r}, expected {status!r}")
    if status == "failed":
        check(isinstance(details.get("error"), str) and details["error"].strip(), "failed fork-result has no error")
    else:
        check("error" not in details, "completed fork-result carries an error")
    session_file = details.get("sessionFile")
    check(isinstance(session_file, str) and os.path.isabs(session_file), "fork-result sessionFile is not an absolute path")
    check(os.path.isfile(session_file), "fork session file does not exist")
    check(Path(session_file).parent == Path(parent_file).parent, "fork session file is not in the parent's session directory")
    header = read_session(session_file)[0]
    check(header.get("type") == "session" and header.get("parentSession") == parent_file,
          "fork session header does not name the parent session file")
    return session_file


def settle(case, grace=1.5, bound=WAIT):
    """Wait until every fork process has exited, then a grace period for late deliveries."""
    deadline = time.monotonic() + bound
    while any(alive(pid) for pid in case.child_pids()):
        check(time.monotonic() < deadline, "fork processes did not exit")
        time.sleep(0.05)
    time.sleep(grace)


def check_no_children(case, since=None, bound=STOP_BOUND):
    start = since if since is not None else time.monotonic()
    while True:
        live = [pid for pid in case.child_pids() if alive(pid)]
        if not live:
            return
        if time.monotonic() - start > bound:
            for pid in live:
                kill_as_node(pid)
            raise Fail(f"fork processes still running {bound:.0f}s later: {live}")
        time.sleep(0.05)


# ---------------------------------------------------------------- cases

def parent_script(prefix, fork_calls, after_text, extra=None):
    """Parent model: the fork prompt -> fork call(s); fork tool results -> after_text;
    anything that already contains a fork result -> an acknowledgement."""
    def script(case, body, pid):
        if pid != case.parent_pid:
            return case.child_script(case, body, pid)
        msgs = convo(body)
        last = msgs[-1] if msgs else {}
        text = content_text(last.get("content"))
        if extra:
            answer = extra(case, body, last, text)
            if answer:
                return answer
        if "fork-result" in all_text(body) or re.search(rf"{prefix}-(CHILD|ANSWER)", all_text(body)):
            if last.get("role") != "tool":
                return ("text", f"{prefix}-ACK")
        if last.get("role") == "user" and f"{prefix}-FORK" in text:
            return ("tools", [("fork", {"task": task}) for task in fork_calls])
        if last.get("role") == "tool":
            return ("text", after_text)
        return ("text", f"{prefix}-ASSIST {text[:24]}")
    return script


def own_task(body, tasks):
    """Which of `tasks` this fork was given (the one after the forking message)."""
    msgs = convo(body)
    for i, m in enumerate(msgs):
        if m.get("role") == "assistant" and any(c.get("function", {}).get("name") == "fork" for c in m.get("tool_calls") or []):
            later = "\n".join(content_text(x.get("content")) for x in msgs[i + 1:])
            return [t for t in tasks if t in later]
    return []


def case_basic_fork(case, run):
    task = "BF-TASK: report the codename you were told"
    case.child_script = None

    def child(case, body, pid):
        case.wait_until(lambda: len(case.parent_events("agent_end")) >= 2, "the parent's forking run to end", 20)
        return ("text", "BF-CHILD-ANSWER codename ORCHID")

    case.child_script = child
    case.script = parent_script("BF", [task], "BF-PARENT-AFTER continuing on my own")
    parent = run.start("fork-test/scripted-a")
    parent.send({"type": "set_model", "provider": "fork-test", "modelId": "scripted-b"})
    parent.send({"type": "set_thinking_level", "level": "high"})
    parent.prompt("BF-USER-1 remember the codename ORCHID")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    parent.prompt("BF-USER-2 BF-FORK please fork a side task")
    parent.wait_idle_runs(3)
    parent_file = run.session_file(parent)

    fork_id = check_fork_tool_result(parent)[0]
    children = case.requesting_children()
    check(len(children) == 1, f"expected one fork process, saw {len(children)}")
    child = children[0]
    first = check_inherited(case, child, forking_request(case, "BF-FORK"), task)
    check_never_sees(case, child, ["BF-PARENT-AFTER", "BF-ACK"])
    check(first["body"].get("model") == "scripted-b", "the fork does not use the parent's current model")
    check(first["body"].get("reasoning_effort") == "high", "the fork does not use the parent's thinking level")
    check("fork" in tool_names(forking_request(case, "BF-FORK")["body"]), "the parent has no fork tool")
    for r in case.child_requests():
        check("fork" not in tool_names(r["body"]), "the fork tool is available inside a fork")
        check("hold" in tool_names(r["body"]), "the fork did not load the user's installed extensions")
    check(run.cli_matches(child), "the fork is not running the parent's pi CLI")

    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result in the parent session, found {len(results)}")
    check_result_entry(results[0], fork_id, "completed", parent_file)
    check("BF-CHILD-ANSWER codename ORCHID" in entry_text(results[0]), "fork-result does not contain the fork's final answer")
    # The parent was idle when the fork finished: the result started a new run.
    runs = parent.events("agent_start")
    check(len(runs) == 3, f"the result did not start exactly one new parent run ({len(runs)} runs)")
    seen = [r for r in case.parent_requests() if "BF-CHILD-ANSWER codename ORCHID" in all_text(r["body"])]
    check(seen, "the parent's model never saw the fork's result")
    check_no_children(case)


def case_deliver_while_running(case, run):
    task = "DR-TASK: answer while the parent is busy"

    def child(case, body, pid):
        # Answer only once the parent is inside its long-running tool.
        case.wait_until(lambda: case.parent_events("hold_start"), "the parent's hold tool", 30)
        return ("text", "DR-CHILD-ANSWER ready")

    state = {"held": False}

    def script(case, body, pid):
        if pid != case.parent_pid:
            return child(case, body, pid)
        msgs = convo(body)
        last = msgs[-1]
        everything = all_text(body)
        if "DR-CHILD-ANSWER" in everything:
            return ("text", "DR-ACK")
        if last.get("role") == "user":
            return ("tools", [("fork", {"task": task})])
        if last.get("role") == "tool" and not state["held"]:
            state["held"] = True
            return ("tools", [("hold", {"key": "busy"})])
        return ("text", "DR-PARENT-DONE without the result")

    case.script = script
    parent = run.start("fork-test/scripted-a")
    parent.prompt("DR-USER DR-FORK fork and keep working")
    run.require_fork_tool()
    # The fork answers while `hold` runs; release the tool once the fork has finished.
    case.wait_until(lambda: case.child_requests(), "the fork's model request")
    case.wait_until(lambda: [e for e in case.parent_events("hold_start")], "the parent's hold tool")
    settle(case)
    check(not parent.events("agent_end"), "the parent run ended before the fork finished")
    case.gate("hold:busy").set()
    parent.wait_idle_runs(1)
    parent_file = run.session_file(parent)
    check(len(parent.events("agent_start")) == 1, "the result was not delivered inside the running parent run")
    holds = parent.tool_ends("hold")
    check(len(holds) == 1 and not holds[0].get("isError"), "the executing tool was interrupted")
    check("released" in content_text(holds[0].get("result", {}).get("content")), "the executing tool did not run to completion")
    seen = [r for r in case.parent_requests() if "DR-CHILD-ANSWER ready" in all_text(r["body"])]
    check(seen, "the parent's model never saw the fork's result during the run")
    fork_id = check_fork_tool_result(parent)[0]
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], fork_id, "completed", parent_file)
    check_no_children(case)


def case_compacted_context(case, run):
    task = "CC-TASK: summarise what we decided"

    def child(case, body, pid):
        return ("text", "CC-CHILD-ANSWER decided")

    case.child_script = child
    case.script = parent_script("CC", [task], "CC-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("CC-USER-1 an early detail that compaction drops")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    parent.prompt("CC-USER-2 a second early detail")
    parent.wait_idle_runs(2)
    parent.send({"type": "compact"})
    parent.prompt("CC-USER-3 CC-FORK fork now")
    parent.wait_idle_runs(4)
    request = forking_request(case, "CC-FORK")
    text = all_text(request["body"])
    check("COMPACTED_CONTEXT-SUMMARY" in text and "CC-USER-1" not in text, "scenario: the parent's context was not compacted")
    child_pid = case.child_pids()[0]
    check_inherited(case, child_pid, request, task)
    check_never_sees(case, child_pid, ["CC-PARENT-AFTER"])
    parent_file = run.session_file(parent)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    check_no_children(case)


def case_parallel_forks(case, run):
    tasks = [f"PF-TASK-{n}: investigate area {n}" for n in (1, 2, 3)]

    def child(case, body, pid):
        mine = own_task(body, tasks)
        if len(mine) != 1:
            return ("text", "PF-CONFUSED")
        n = mine[0][len("PF-TASK-")]
        # Finish in reverse order of the calls.
        case.wait_until(lambda: len(case.child_pids()) >= 3, "three forks", 20)
        time.sleep({"1": 1.2, "2": 0.6, "3": 0.0}[n])
        return ("text", f"PF-ANSWER-{n} area {n} is fine")

    case.child_script = child
    case.script = parent_script("PF", tasks, "PF-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("PF-USER PF-FORK fork three investigations")
    run.require_fork_tool()
    parent_file = None
    parent.wait_idle_runs(1)
    case.wait_until(lambda: len(fork_results(run.session_file(parent))) >= 3, "three fork results", WAIT)
    settle(case)
    parent_file = run.session_file(parent)
    children = case.requesting_children()
    check(len(children) == 3, f"expected three fork processes, saw {len(children)}")
    for pid in children:
        first = case.first_request_of(pid)
        mine = own_task(first["body"], tasks)
        check(len(mine) == 1, "a fork was not given exactly its own task")
        check_inherited(case, pid, forking_request(case, "PF-FORK"), mine[0], [t for t in tasks if t != mine[0]])
    # Map tool call -> task -> fork id -> result content.
    ends = parent.tool_ends("fork")
    check(len(ends) == 3, "expected three fork tool results")
    starts = {i.get("toolCallId"): i.get("args", {}).get("task") for i in parent.events("tool_execution_start") if i.get("toolName") == "fork"}
    fork_task = {}
    for item in ends:
        details = item.get("result", {}).get("details") or {}
        fork_task[details.get("forkId")] = starts.get(item.get("toolCallId"))
    check(len(set(fork_task)) == 3, "fork ids are not unique")
    results = fork_results(parent_file)
    check(len(results) == 3, f"expected three fork-results, found {len(results)}")
    for entry in results:
        fork_id = (entry.get("details") or {}).get("forkId")
        check(fork_id in fork_task, "a fork-result names an unknown fork id")
        check_result_entry(entry, fork_id, "completed", parent_file)
        n = fork_task[fork_id][len("PF-TASK-")]
        check(f"PF-ANSWER-{n} area {n} is fine" in entry_text(entry), "a fork-result carries another fork's answer")
    parent.wait_idle_runs(len(parent.events("agent_start")))
    seen = "\n".join(all_text(r["body"]) for r in case.parent_requests())
    for n in (1, 2, 3):
        check(f"PF-ANSWER-{n}" in seen, "the parent's model did not see every fork result")
    check_no_children(case)


def case_failed_forks(case, run):
    tasks = ["FF-TASK-ERROR: this model call fails", "FF-TASK-KILL: this process is killed",
             "FF-TASK-EXIT: this process exits abnormally"]

    def child(case, body, pid):
        mine = own_task(body, tasks)
        if mine == [tasks[0]]:
            return ("error", "FF-MODEL-ERROR upstream exploded")
        if mine == [tasks[1]]:
            with case.lock:
                case.kill_pid = pid
                case.lock.notify_all()
            case.gate("never").wait(WAIT)
            return ("text", "FF-UNREACHABLE")
        if mine == [tasks[2]]:
            with case.lock:
                case.exit_pids.add(pid)
            return ("text", "FF-EXIT-ANSWER that never counts")
        return ("text", "FF-CONFUSED")

    case.kill_pid = None
    case.child_script = child
    case.script = parent_script("FF", tasks, "FF-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("FF-USER FF-FORK start three forks that will fail")
    run.require_fork_tool()
    pid = case.wait_until(lambda: case.kill_pid, "the fork that will be killed")
    kill_as_node(pid)
    parent_file = run.session_file(parent)
    case.wait_until(lambda: len(fork_results(parent_file)) >= 3, "three fork results")
    settle(case)
    results = fork_results(parent_file)
    check(len(results) == 3, f"expected three fork-results, found {len(results)}")
    ends = parent.tool_ends("fork")
    starts = {i.get("toolCallId"): i.get("args", {}).get("task") for i in parent.events("tool_execution_start") if i.get("toolName") == "fork"}
    fork_task = {(i.get("result", {}).get("details") or {}).get("forkId"): starts.get(i.get("toolCallId")) for i in ends}
    for entry in results:
        details = entry.get("details") or {}
        check(details.get("forkId") in fork_task, "a fork-result names an unknown fork id")
        check(details.get("status") == "failed", "a failed fork was not reported as failed")
        check(entry.get("display") is True, "fork-result message is not displayed")
        error = details.get("error")
        check(isinstance(error, str) and error.strip(), "failed fork-result has no error")
        check(error in entry_text(entry), "failed fork-result content does not include the reason")
        if fork_task[details["forkId"]] == tasks[0]:
            check("FF-MODEL-ERROR upstream exploded" in error, "the model error is not the reported reason")
    parent.wait_idle_runs(len(parent.events("agent_start")))
    seen = "\n".join(all_text(r["body"]) for r in case.parent_requests())
    check("FF-MODEL-ERROR upstream exploded" in seen, "the parent's model did not see the failure")
    check_no_children(case)


def held_child(case, body, pid):
    case.gate("child-release").wait(WAIT)
    return ("text", case.marker + "-CHILD-ANSWER late")


def case_quit_stops_forks(case, run):
    case.marker = "QS"
    case.child_script = held_child
    case.script = parent_script("QS", ["QS-TASK: a long investigation"], "QS-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("QS-USER QS-FORK fork then quit")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    case.wait_until(lambda: case.child_requests(), "the fork's model request")
    parent_file = run.session_file(parent)
    parent.proc.stdin.close()  # RPC end of input: pi shuts the session down and exits
    shutdown = case.wait_until(lambda: case.parent_events("session_shutdown"), "the parent's session_shutdown")
    check(shutdown[0].get("reason") == "quit", "scenario: the parent did not quit")
    check_no_children(case, since=shutdown[0]["t"])
    case.gate("child-release").set()
    parent.proc.wait(timeout=15)
    time.sleep(1.5)
    check(not fork_results(parent_file), "a stopped fork delivered a result")


def case_switch_stops_forks(case, run):
    case.marker = "SS"
    case.child_script = held_child
    case.script = parent_script("SS", ["SS-TASK: a long investigation"], "SS-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    # Session A forks, then the user starts a new session B.
    parent.prompt("SS-USER SS-FORK fork then switch")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    case.wait_until(lambda: len(case.requesting_children()) >= 1, "the fork's model request")
    file_a = run.session_file(parent)
    parent.send({"type": "new_session"})
    shutdown = case.wait_until(lambda: case.parent_events("session_shutdown"), "the parent's session_shutdown")
    check(shutdown[0].get("reason") == "new", "scenario: the session was not replaced")
    check_no_children(case, since=shutdown[0]["t"])
    # Session B forks, then the user resumes session A.
    parent.prompt("SS-USER-2 SS-FORK fork again in the new session")
    parent.wait_idle_runs(2)
    case.wait_until(lambda: len(case.requesting_children()) >= 2, "the second fork's model request")
    file_b = run.session_file(parent)
    check(file_b != file_a, "scenario: no new session")
    parent.send({"type": "switch_session", "sessionPath": file_a})
    shutdown = case.wait_until(lambda: len(case.parent_events("session_shutdown")) >= 2 and case.parent_events("session_shutdown"),
                               "the second session_shutdown")
    check(shutdown[1].get("reason") == "resume", "scenario: the session was not resumed")
    check_no_children(case, since=shutdown[1]["t"])
    case.gate("child-release").set()
    parent.prompt("SS-USER-3 anything new?")
    parent.wait_idle_runs(3)
    time.sleep(1.5)
    check(run.session_file(parent) == file_a, "scenario: session A was not resumed")
    check(not fork_results(file_a), "a stopped fork delivered a result to a session")
    check(not fork_results(file_b), "a stopped fork delivered a result to a session")
    later = [r for r in case.parent_requests() if "SS-USER-3" in all_text(r["body"])]
    check(later and all("SS-CHILD-ANSWER" not in all_text(r["body"]) for r in later),
          "a stopped fork's answer reached the resumed session")


def case_reload_keeps_forks(case, run):
    case.marker = "RK"
    case.child_script = held_child
    case.script = parent_script("RK", ["RK-TASK: survive a reload"], "RK-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("RK-USER RK-FORK fork then reload")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    case.wait_until(lambda: case.child_requests(), "the fork's model request")
    child_pid = case.child_pids()[0]
    parent.prompt("/verifier-reload")
    case.wait_until(lambda: [e for e in case.parent_events("session_start") if e.get("reason") == "reload"], "the reload")
    time.sleep(1.0)
    check(alive(child_pid), "the fork was stopped by /reload")
    case.gate("child-release").set()
    parent_file = run.session_file(parent)
    case.wait_until(lambda: fork_results(parent_file), "the fork's result after reload")
    first = fork_results(parent_file)[0]
    check((first.get("details") or {}).get("status") == "completed",
          "after /reload the still-running fork was reported as "
          f"{(first.get('details') or {}).get('status')!r}: {(first.get('details') or {}).get('error')}")
    case.wait_until(lambda: [r for r in case.parent_requests() if "RK-CHILD-ANSWER late" in all_text(r["body"])],
                    "the parent's model to see the result")
    settle(case)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected exactly one fork-result after reload, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    check_no_children(case)


def case_empty_task(case, run):
    case.marker = "ET"

    def child(case, body, pid):
        return ("text", "ET-CHILD-ANSWER real task done")

    state = {"step": 0}

    def script(case, body, pid):
        if pid != case.parent_pid:
            return child(case, body, pid)
        msgs = convo(body)
        last = msgs[-1]
        if "ET-CHILD-ANSWER" in all_text(body):
            return ("text", "ET-ACK")
        if last.get("role") == "user" and state["step"] == 0:
            state["step"] = 1
            return ("tools", [("fork", {"task": "   "})])
        if last.get("role") == "tool" and state["step"] == 1:
            state["step"] = 2
            return ("tools", [("fork", {"task": "ET-TASK: a real task after the rejected one"})])
        return ("text", "ET-PARENT-AFTER")

    case.script = script
    parent = run.start("fork-test/scripted-a")
    parent.prompt("ET-USER ET-FORK fork nothing, then something")
    run.require_fork_tool()
    parent.wait_idle_runs(2)
    ends = parent.tool_ends("fork")
    check(len(ends) == 2, f"expected two fork calls, saw {len(ends)}")
    check(ends[0].get("isError"), "an empty task was not rejected with an error result")
    check(not ends[1].get("isError"), "a valid fork after a rejected one failed")
    children = case.requesting_children()
    check(len(children) == 1, f"the empty task started a fork ({len(children)} fork processes for one valid task)")
    parent_file = run.session_file(parent)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent, 1)[0], "completed", parent_file)
    check_no_children(case)


def big_answer():
    """~100k UTF-16 code units: CJK, emoji (surrogate pairs), combining marks, newlines."""
    unit = "第{n}段：分叉结果 🧪🔀 e\u0301te\u0301 ✓ line {n}\n"
    body = "".join(unit.format(n=n) for n in range(3500))
    return "FA-FINAL-BEGIN\n" + body + "FA-FINAL-END"


def case_final_answer(case, run):
    task = "FA-TASK: use a tool, then write the long final report"
    answer = big_answer()
    case.gate("hold:fa").set()

    def child(case, body, pid):
        msgs = convo(body)
        if msgs and msgs[-1].get("role") == "tool" and "held fa" in content_text(msgs[-1].get("content")):
            return ("text", answer)
        return ("tools", [("hold", {"key": "fa"})])

    case.child_script = child
    case.script = parent_script("FA", [task], "FA-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("FA-USER FA-FORK fork a long report")
    run.require_fork_tool()
    parent_file = run.session_file(parent)
    case.wait_until(lambda: fork_results(parent_file), "the fork's result")
    settle(case)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    session_file = check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    check(answer in entry_text(results[0]), "fork-result does not contain the fork's final answer verbatim")
    fork_entries = [e for e in read_session(session_file) if e.get("type") == "message"]
    check(fork_entries and fork_entries[-1]["message"].get("role") == "assistant"
          and answer in content_text(fork_entries[-1]["message"].get("content")),
          "the fork's session file does not record the fork's final answer")
    parent.wait_idle_runs(len(parent.events("agent_start")))
    check(any(answer in all_text(r["body"]) for r in case.parent_requests()),
          "the parent's model did not see the fork's final answer verbatim")
    check_no_children(case)


def case_parent_killed(case, run):
    case.marker = "PK"
    case.child_script = held_child
    case.script = parent_script("PK", ["PK-TASK: a long investigation"], "PK-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("PK-USER PK-FORK fork then die")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    case.wait_until(lambda: case.requesting_children(), "the fork's model request")
    killed_at = time.monotonic()
    kill_as_node(parent.proc.pid)  # SIGKILL: no session_shutdown, no extension cleanup
    parent.proc.wait(timeout=10)
    check(not case.parent_events("session_shutdown"), "scenario: the parent shut down instead of dying")
    check_no_children(case, since=killed_at)


def case_deliver_at_run_end(case, run):
    task = "RE-TASK: finish while the parent writes its last reply"

    def final_request_seen():
        return [r for r in case.parent_requests() if convo(r["body"]) and convo(r["body"])[-1].get("role") == "tool"]

    def child(case, body, pid):
        # Answer only once the parent is producing the last response of its run.
        case.wait_until(final_request_seen, "the parent's final request", 30)
        return ("text", "RE-CHILD-ANSWER in time")

    def script(case, body, pid):
        if pid != case.parent_pid:
            return child(case, body, pid)
        msgs = convo(body)
        last = msgs[-1]
        if "RE-CHILD-ANSWER in time" in all_text(body):
            return ("text", "RE-ACK")
        if last.get("role") == "user":
            return ("tools", [("fork", {"task": task})])
        # The run's last response: hold it until the fork has finished and reported.
        case.wait_until(lambda: case.requesting_children(), "the fork's model request", 30)
        settle(case, grace=3.0, bound=30)
        return ("text", "RE-PARENT-FINAL no more tools")

    case.script = script
    parent = run.start("fork-test/scripted-a")
    parent.prompt("RE-USER RE-FORK fork at the end of a run")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    time.sleep(1.5)
    parent_file = run.session_file(parent)
    check(len(parent.events("agent_start")) == 1,
          "the result was not delivered inside the run that was still running when the fork finished")
    check(any("RE-CHILD-ANSWER in time" in all_text(r["body"]) for r in case.parent_requests()),
          "the parent's model never saw the fork's result")
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    check_no_children(case)


def case_fork_beside_running_tool(case, run):
    task = "BT-TASK: start while a sibling tool is still running"

    def child(case, body, pid):
        return ("text", "BT-CHILD-ANSWER started early")

    def script(case, body, pid):
        if pid != case.parent_pid:
            return child(case, body, pid)
        msgs = convo(body)
        last = msgs[-1]
        if "BT-CHILD-ANSWER started early" in all_text(body):
            return ("text", "BT-ACK")
        if last.get("role") == "user":
            return ("tools", [("hold", {"key": "sibling"}), ("fork", {"task": task})])
        return ("text", "BT-PARENT-AFTER")

    case.script = script
    parent = run.start("fork-test/scripted-a")
    parent.prompt("BT-USER BT-FORK fork next to a long tool")
    run.require_fork_tool()
    # The sibling tool runs until the fork has made its first model request.
    try:
        case.wait_until(lambda: case.requesting_children(), "the fork to start while its sibling tool runs", 20)
        sibling_ended_first = bool(case.parent_events("hold_end"))
    finally:
        case.gate("hold:sibling").set()
    check(not sibling_ended_first, "scenario: the sibling tool ended first")
    parent_file = run.session_file(parent)
    case.wait_until(lambda: fork_results(parent_file), "the fork's result")
    settle(case)
    child_pid = case.requesting_children()[0]
    check_inherited(case, child_pid, forking_request(case, "BT-FORK"), task)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    parent.wait_idle_runs(len(parent.events("agent_start")))
    check(any("BT-CHILD-ANSWER started early" in all_text(r["body"]) for r in case.parent_requests()),
          "the parent's model never saw the fork's result")
    check_no_children(case)


def case_deliver_during_compaction(case, run):
    task = "DC-TASK: finish while the parent compacts"

    def child(case, body, pid):
        case.wait_until(lambda: case.summary_started, "the parent's compaction", 30)
        return ("text", "DC-CHILD-ANSWER during compaction")

    def hold_summary(case, body, pid):
        with case.lock:
            case.summary_started = True
            case.lock.notify_all()
        # Keep the compaction running until the fork has finished and reported.
        settle(case, grace=1.0, bound=30)

    case.summary_started = False
    case.child_script = child
    case.script = parent_script("DC", [task], "DC-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("DC-USER-1 some earlier context to compact")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    parent.prompt("DC-USER-2 DC-FORK fork, then the user compacts")
    parent.wait_idle_runs(2)
    case.wait_until(lambda: case.requesting_children(), "the fork's model request")
    case.summary_hook = hold_summary
    parent.send({"type": "compact"}, timeout=60)
    parent_file = run.session_file(parent)
    case.wait_until(lambda: fork_results(parent_file), "the fork's result after the compaction")
    case.wait_until(lambda: [r for r in case.parent_requests() if "DC-CHILD-ANSWER during compaction" in all_text(r["body"])],
                    "the parent's model to see the result")
    parent.wait_idle_runs(len(parent.events("agent_start")))
    time.sleep(1.0)
    entries = read_session(parent_file)
    check(any(e.get("type") == "compaction" for e in entries), "scenario: the parent did not compact")
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    # The result must survive the compaction: a later prompt's context still carries it.
    runs = len(parent.events("agent_start"))
    parent.prompt("DC-USER-3 after the compaction")
    parent.wait_idle_runs(runs + 1)
    later = [r for r in case.parent_requests() if "DC-USER-3" in all_text(r["body"])]
    check(later and "DC-CHILD-ANSWER during compaction" in all_text(later[0]["body"]),
          "the fork's result is missing from the parent's context after the compaction")
    check(len(fork_results(parent_file)) == 1, "the fork's result was delivered more than once")
    check_no_children(case)


def case_finish_during_reload(case, run):
    case.marker = "FR"
    case.child_script = held_child
    case.script = parent_script("FR", ["FR-TASK: finish while extensions reload"], "FR-PARENT-AFTER")
    parent = run.start("fork-test/scripted-a")
    parent.prompt("FR-USER FR-FORK fork then reload")
    run.require_fork_tool()
    parent.wait_idle_runs(1)
    case.wait_until(lambda: case.requesting_children(), "the fork's model request")

    def during_reload(case, item):
        # The old extension runtime is shutting down for the reload: let the fork finish
        # now, and keep the reload from completing until the fork process has exited.
        if item.get("pid") == case.parent_pid and item.get("event") == "session_shutdown" and item.get("reason") == "reload":
            case.gate("child-release").set()
            settle(case, grace=1.0, bound=30)

    case.event_hook = during_reload
    parent.prompt("/verifier-reload")
    case.wait_until(lambda: [e for e in case.parent_events("session_start") if e.get("reason") == "reload"], "the reload")
    parent_file = run.session_file(parent)
    case.wait_until(lambda: fork_results(parent_file), "the fork's result after the reload")
    case.wait_until(lambda: [r for r in case.parent_requests() if "FR-CHILD-ANSWER late" in all_text(r["body"])],
                    "the parent's model to see the result")
    parent.wait_idle_runs(len(parent.events("agent_start")))
    time.sleep(1.5)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected exactly one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)


def case_interrupted_delivery(case, run):
    task = "ID-TASK: finish while the parent is busy, then the user interrupts"

    def child(case, body, pid):
        case.wait_until(lambda: case.parent_events("hold_start"), "the parent's hold tool", 30)
        return ("text", "ID-CHILD-ANSWER survives the interrupt")

    state = {"held": False}

    def script(case, body, pid):
        if pid != case.parent_pid:
            return child(case, body, pid)
        msgs = convo(body)
        last = msgs[-1]
        if "ID-CHILD-ANSWER survives the interrupt" in all_text(body):
            return ("text", "ID-ACK")
        if last.get("role") == "user":
            return ("tools", [("fork", {"task": task})])
        if last.get("role") == "tool" and not state["held"]:
            state["held"] = True
            return ("tools", [("hold", {"key": "busy"})])
        return ("text", "ID-PARENT-AFTER")

    case.script = script
    parent = run.start("fork-test/scripted-a")
    parent.prompt("ID-USER ID-FORK fork, stay busy, get interrupted")
    run.require_fork_tool()
    case.wait_until(lambda: case.parent_events("hold_start"), "the parent's hold tool")
    # The fork finishes and reports while the parent is inside `hold`.
    settle(case, grace=1.0)
    check(not any("ID-CHILD-ANSWER" in all_text(r["body"]) for r in case.parent_requests()),
          "scenario: the result reached the model before the interrupt")
    # Escape in pi's interactive mode: discard the queued messages, then abort the run.
    parent.send({"type": "clear_queue"})
    abort_id = parent.send_nowait({"type": "abort"})
    time.sleep(0.5)
    case.gate("hold:busy").set()
    parent.wait_response(abort_id, "abort")
    parent_file = run.session_file(parent)
    case.wait_until(lambda: [r for r in case.parent_requests() if "ID-CHILD-ANSWER survives the interrupt" in all_text(r["body"])],
                    "the parent's model to see the result after the interrupt", 20)
    parent.wait_idle_runs(len(parent.events("agent_start")))
    time.sleep(1.5)
    results = fork_results(parent_file)
    check(len(results) == 1, f"expected exactly one fork-result, found {len(results)}")
    check_result_entry(results[0], check_fork_tool_result(parent)[0], "completed", parent_file)
    check_no_children(case)


# ---------------------------------------------------------------- runner

class Run:
    def __init__(self, case, scratch, env, cwd):
        self.case = case
        self.scratch = scratch
        self.env = env
        self.cwd = cwd
        self.parent = None

    def start(self, model):
        self.parent = Parent(self.case, self.env, self.cwd, ["--model", model])
        return self.parent

    def require_fork_tool(self):
        first = self.case.wait_until(lambda: self.case.parent_requests(), "the parent's first model request")[0]
        check("fork" in tool_names(first["body"]), "the parent has no fork tool (is the extension installed from settings?)")

    def session_file(self, parent):
        state = parent.send({"type": "get_state"})
        path = (state.get("data") or {}).get("sessionFile")
        check(isinstance(path, str) and path, "the parent has no session file")
        return path

    def cli_matches(self, pid):
        # pi's CLI sets process.title to "pi", which replaces argv in /proc (captured while
        # the fork ran). Loading the user's extensions is checked separately.
        args = self.case.cmdlines.get(pid) or []
        return bool(args) and args[0] == "pi"


def run_case(name, output):
    case = Case(name)
    case.child_script = lambda c, b, p: ("text", "UNSCRIPTED")
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(case))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    scratch = Path(tempfile.mkdtemp(prefix="pi-fork-case-", dir="/tmp"))
    harness = Path(tempfile.mkdtemp(prefix="pi-fork-harness-", dir="/tmp"))
    fixture = harness / "fixture.ts"
    shutil.copyfile(HERE / "fixture.ts", fixture)
    harness.chmod(0o755)
    fixture.chmod(0o644)
    agent_dir = scratch / "agent"
    for part in ["agent", "home", "tmp", "work", "bin"]:
        (scratch / part).mkdir()
    (agent_dir / "settings.json").write_text(json.dumps({
        "extensions": [str(fixture), str(EXTENSION)],
        "compaction": {"enabled": False, "keepRecentTokens": 1},
        "retry": {"enabled": False},
    }))
    shim = scratch / "bin/pi"
    shim.write_text(f"#!/bin/sh\nexec {NODE} {CLI} \"$@\"\n")
    shim.chmod(0o755)
    for path in [scratch, *scratch.rglob("*")]:
        os.chown(path, 1000, 1000)
    env = {
        "PATH": f"{scratch / 'bin'}:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "TZ": "UTC",
        "HOME": str(scratch / "home"), "TMPDIR": str(scratch / "tmp"), "PI_CODING_AGENT_DIR": str(agent_dir),
        "PI_FORK_TEST_URL": f"http://127.0.0.1:{server.server_port}",
        "PI_OFFLINE": "1", "PI_TELEMETRY": "0", "PI_NO_LOCAL_LLM": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    run = Run(case, scratch, env, scratch / "work")
    started = time.monotonic()
    passed = False
    try:
        globals()["case_" + name](case, run)
        check(not case.errors, "; ".join(case.errors))
        passed = True
    except Exception as exc:
        case.errors.append(f"{type(exc).__name__}: {exc}" if isinstance(exc, Fail) else traceback.format_exc())
    finally:
        case.closed = True
        for gate in list(case.gates.values()):
            gate.set()
        parent = run.parent
        if parent and parent.proc.poll() is None:
            try:
                parent.proc.stdin.close()
            except OSError:
                pass
            try:
                parent.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                kill_as_node(parent.proc.pid)
        for pid in case.child_pids():
            if alive(pid):
                kill_as_node(pid)
        server.shutdown()
        server.server_close()
    directory = output / name
    directory.mkdir(parents=True, exist_ok=True)
    result = {"name": name, "passed": passed, "errors": case.errors, "cmdlines": {str(k): v for k, v in case.cmdlines.items()},
              "parent_exit": run.parent.proc.returncode if run.parent else None,
              "elapsed_seconds": round(time.monotonic() - started, 2)}
    (directory / "result.json").write_text(json.dumps(result, indent=2))
    (directory / "requests.json").write_text(json.dumps(
        [{"pid": r["pid"], "t": round(r["t"] - started, 3), "body": r["body"]} for r in case.requests], indent=1))
    (directory / "events.json").write_text(json.dumps(case.events, indent=1, default=str))
    if run.parent:
        (directory / "rpc.jsonl").write_text("\n".join(json.dumps(i) for i in run.parent.lines))
        (directory / "stderr.txt").write_text("".join(run.parent.stderr))
    sessions = agent_dir / "sessions"
    if sessions.exists():
        shutil.copytree(sessions, directory / "sessions", symlinks=False, dirs_exist_ok=True)
    shutil.rmtree(scratch, ignore_errors=True)
    shutil.rmtree(harness, ignore_errors=True)
    return result


def main():
    output = Path(sys.argv[sys.argv.index("--output") + 1])
    only = sys.argv[sys.argv.index("--case") + 1].split(",") if "--case" in sys.argv else CASES
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in only:
        result = run_case(name, output)
        print(("PASS " if result["passed"] else "FAIL ") + name + ("" if result["passed"] else ": " + result["errors"][0][:500]), flush=True)
        results.append(result)
    summary = {"cases": [r["name"] for r in results], "passed": [r["name"] for r in results if r["passed"]],
               "failed": [r["name"] for r in results if not r["passed"]], "all": list(CASES)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    return 0 if len(summary["passed"]) == len(CASES) and summary["cases"] == CASES else 1


if __name__ == "__main__":
    sys.exit(main())
