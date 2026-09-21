#!/usr/bin/env python3
"""Deterministic model input; real Pi tools, loop, provider adapters and persistence.

A trusted parent checks actual HTTP requests. It never imports candidate code,
rewrites candidate context, or supplies missing feature behavior.
"""
from __future__ import annotations
import argparse
import json
import os
import pwd
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CASES = ["ordinary", "empty", "rollover", "repeated", "resume", "notes", "history", "batch", "isolation", "responses", "clear_resume", "repeated_unchanged"]
TOOLS = {"new_context", "notes_write", "notes_read", "history_search", "history_read"}


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


def call(name, **arguments):
    return {"id": "call_" + uuid.uuid4().hex, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


def calls(*items):
    return {"tool_calls": [dict(item, index=i) for i, item in enumerate(items)]}


def result(body):
    assert body["messages"][-1]["role"] == "tool", "Expected tool result in the next actual model request"
    return json.loads(text(body["messages"][-1]))


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
        self.correction = "Continue; keep the newly required compatibility constraint " + uuid.uuid4().hex
        self.system = "System invariant " + uuid.uuid4().hex
        self.summary = "缓存已排除。继续检查连接池。" + uuid.uuid4().hex
        self.hypothesis = "assistant-hypothesis-" + uuid.uuid4().hex
        self.anchor = "evidence-anchor-" + uuid.uuid4().hex
        self.secret = "original-receipt-" + uuid.uuid4().hex
        self.evidence = {"old": self.anchor + "\n" + "古🙂e\u0301 log\n" * 800 + self.secret,
                         "noise": "unrelated-original-" + uuid.uuid4().hex + "\n" + "unrelated log\n" * 800,
                         "side": "SIDE-" + uuid.uuid4().hex}
        self.current_marker = "new-window-assistant-" + uuid.uuid4().hex
        self.events, self.requests, self.errors, self.served, self.emitted = [], [], [], [], []
        self.saved, self.checks = {}, []
        self.done = False
        self.script = None

    def checked(self, name):
        self.checks.append({"name":name,"request":len(self.requests)})

    def check_fresh(self, body, *, notes=True):
        value = all_text(body)
        assert self.goal in value and self.system in value, "Goal/system instructions lost"
        if notes: assert self.summary in value, "Latest working notes not carried into fresh context"
        assert self.secret not in value and self.anchor not in value, "Old evidence still in active context"
        assert self.evidence["noise"].splitlines()[0] not in value, "Unrelated old record reloaded"
        assert self.hypothesis not in value, "Old assistant text still in active context"
        assert all(c["id"] not in value for c in self.emitted), "Earlier tool-call/result batch remains in fresh context"
        self.checked("next_request_is_fresh")

    def initial(self, body):
        names = {t["function"]["name"] for t in body.get("tools", [])}
        if self.name == "ordinary": assert not (TOOLS & names), "Feature enabled without extension"
        else: assert TOOLS <= names, "Missing public tools: " + str(sorted(TOOLS - names))

    def setup_window(self):
        body = yield dict(calls(call("evidence", key="old"),call("evidence",key="noise")), content=self.hypothesis)
        assert self.secret in all_text(body), "Evidence never reached real model input"
        body = yield calls(call("notes_write", text=self.summary))
        body = yield calls(call("new_context"))
        self.check_fresh(body)
        return body

    def recover(self, query, expected):
        body = yield calls(call("history_search",query=query))
        items = result(body)["items"]
        assert items, "Search did not locate original record"
        # Metadata, search order and previews are not fixed by the contract.
        for item in items:
            identity = {key:item[key] for key in ["window_id","item_id"]}
            assert all(isinstance(v,str) and v for v in identity.values()), "History IDs must be usable opaque strings"
            body = yield calls(call("history_read",**identity))
            if expected in result(body)["text"]:
                self.checked("original_record_recovered")
                return body, identity
        raise AssertionError("No matching item exposes the complete original record")

    def script_main(self, phase=0):
        body = yield
        self.initial(body)
        if self.name == "ordinary":
            body = yield calls(call("evidence",key="side"))
            assert self.evidence["side"] in all_text(body)
        elif self.name == "empty":
            body = yield calls(call("new_context"))
            self.check_fresh(body,notes=False)
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
                assert result(body)["text"] == "", "Empty replacement did not clear working notes"
                body = yield calls(call("new_context"))
                self.check_fresh(body,notes=False)
                assert self.saved["old_note"] not in all_text(body), "Cleared conclusion resurrected on reset"
            else:
                self.check_fresh(body,notes=False)
                assert self.saved["old_note"] not in all_text(body), "Cleared conclusion resurrected on restart"
                body = yield calls(call("notes_read"))
                assert result(body)["text"] == "", "Cleared notes not persisted"
                body = yield calls(call("history_read",**self.saved["identity"]))
                assert self.evidence["old"] in result(body)["text"], "Clearing working notes destroyed original evidence"
                self.checked("empty_note_replacement_survives_restart_without_erasing_history")
        elif phase == 1:
            if self.name == "resume":
                value=all_text(body)
                assert self.summary in value and self.current_marker in value, "Resume lost notes or current-window conversation"
                assert self.correction in value and self.secret not in value, "Resume lost correction or restored discarded history"
                body = yield calls(call("notes_read"))
                assert result(body)["text"] == self.summary
                body = yield calls(call("history_read",**self.saved["identity"]))
                assert self.evidence["old"] in result(body)["text"], "IDs/evidence did not survive real process restart"
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                assert self.correction in all_text(body), "Later user correction lost on next transition"
                self.checked("restart_restores_active_state_and_stable_history")
            else:
                value=all_text(body)
                assert self.summary not in value and self.secret not in value
                body = yield calls(call("notes_read"))
                assert self.summary not in all_text(body), "Notes leaked into second session"
                body = yield calls(call("history_search",query=self.anchor))
                # The current search call can itself contain this query. Inspect
                # returned records instead of imposing an empty-result convention.
                for item in result(body)["items"]:
                    identity={k:item[k] for k in ["window_id","item_id"]}
                    body = yield calls(call("history_read",**identity))
                    assert self.secret not in result(body)["text"], "Other session's original record is searchable"
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
                body,_=yield from self.recover(self.hypothesis,self.hypothesis)
                body,_=yield from self.recover(self.nonce,self.goal)
            if self.name == "resume":
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                body = yield dict(calls(call("notes_read")),content=self.current_marker)
                assert result(body)["text"] == self.summary
        elif self.name == "repeated_unchanged":
            # Reproduce the live model's repeated reset pattern, without judging
            # its strategy or requiring the extension to rewrite working notes.
            self.summary += "\n下一步调用 new_context，然后继续核验。"
            body = yield from self.setup_window()
            body, identity = yield from self.recover(self.anchor, self.evidence["old"])
            for index in range(10):
                marker = "between-resets-" + uuid.uuid4().hex
                body = yield dict(calls(call("notes_read")), content=marker)
                assert result(body)["text"] == self.summary, "Repeated reset changed working notes"
                body = yield calls(call("new_context"))
                self.check_fresh(body)
                assert marker not in all_text(body), "Repeated reset retained intervening assistant text"
            body = yield calls(call("notes_read"))
            assert result(body)["text"] == self.summary, "Unchanged working notes lost after eleven resets"
            body = yield calls(call("history_read", **identity))
            assert self.evidence["old"] in result(body)["text"], "Old evidence/IDs lost after eleven resets"
            body = yield calls(call("evidence", key="side"))
            assert self.evidence["side"] in all_text(body), "Tool loop stopped after repeated resets"
            self.checked("eleven_resets_preserve_unchanged_notes_and_original_evidence")
        elif self.name == "notes":
            self.summary="进展🙂e\u0301\n"*700
            body = yield calls(call("notes_write",text=self.summary))
            body = yield calls(call("notes_read"))
            assert result(body)["text"] == self.summary, "Working notes changed or truncated"
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            previous=self.summary
            self.summary="替换后的结论\n"+uuid.uuid4().hex
            body = yield calls(call("notes_write",text=self.summary))
            body = yield calls(call("notes_read"))
            assert result(body)["text"] == self.summary, "Write did not replace notes"
            body = yield calls(call("new_context"))
            self.check_fresh(body)
            assert previous not in all_text(body)
        elif self.name == "history":
            body = yield from self.setup_window()
            # A receipt near the end of a long record must lead back to that record.
            body,_=yield from self.recover(self.secret,self.evidence["old"])
            assert self.evidence["noise"].splitlines()[0] not in all_text(body)
            body,_=yield from self.recover(self.hypothesis,self.hypothesis)
            # Verify original assistant tool arguments, not only prose.
            body,identity=yield from self.recover('"old"','"old"')
            assert "evidence" in result(body)["text"], "Assistant tool-call name was not archived"
        elif self.name == "batch":
            body = yield from self.setup_window()
            previous=self.summary
            self.summary="Evidence discovered in the switching batch "+uuid.uuid4().hex
            batch=[call("new_context"),call("evidence",key="side"),call("notes_write",text=self.summary),call("new_context")]
            body = yield calls(*batch)
            self.check_fresh(body)
            assert previous not in all_text(body)
            assert self.evidence["side"] not in all_text(body), "Switching batch output retained in the new window"
            assert self.served.count("side")==1, "Requested side-effect tool skipped or repeated"
            for requested in batch:
                ends=[e for e in self.events if e.get("type")=="tool_execution_end" and e.get("toolCallId","").split("|")[0]==requested["id"]]
                assert len(ends)==1 and not ends[0]["isError"], "Batch did not complete each requested tool exactly once"
            body=yield calls(call("notes_read"))
            assert result(body)["text"]==self.summary
            body,_=yield from self.recover(self.evidence["side"],self.evidence["side"])
            self.checked("whole_batch_committed_before_transition")
        else: raise AssertionError("Unimplemented scenario")
        self.done=True
        yield {"content":"VERIFIED-"+self.nonce}

    def respond(self, wire):
        body=normalize(wire)
        self.requests.append(body)
        pair_check(body)
        assert len(self.requests)<120, "Unexpected repeated model calls"
        delta=self.script.send(body)
        self.emitted.extend(delta.get("tool_calls",[]))
        return delta


def response_sse(delta):
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
                   "usage":{"input_tokens":100,"output_tokens":10,"total_tokens":110}}})
    return "".join("event: "+e["type"]+"\ndata: "+json.dumps(e,ensure_ascii=False)+"\n\n" for e in events).encode()


def handler(scenario):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_POST(self):
            try:
                body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                content_type="text/plain"
                if self.path=="/event":scenario.events.append(body);payload=b"ok"
                elif self.path=="/evidence":
                    scenario.served.append(body["key"])
                    payload=scenario.evidence[body["key"]].encode()
                elif self.path in ["/v1/chat/completions","/v1/responses"]:
                    delta=scenario.respond(body)
                    content_type="text/event-stream"
                    if self.path.endswith("responses"):payload=response_sse(delta)
                    else:
                        chunks=[{"id":"chatcmpl-local","object":"chat.completion.chunk","created":1,"model":"scripted",
                                 "choices":[{"index":0,"delta":d,"finish_reason":f}]} for d,f in [(dict(role="assistant",**delta),None),({},"tool_calls" if "tool_calls" in delta else "stop")]]
                        payload=("".join("data: "+json.dumps(c,ensure_ascii=False)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()
                else:raise AssertionError("Unexpected endpoint: "+self.path)
                self.send_response(200);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
            except Exception as exc:
                scenario.errors.append(repr(exc))
                payload=json.dumps({"error":{"message":repr(exc),"type":"invalid_request_error"}}).encode()
                try:
                    self.send_response(400);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
                except OSError:pass
    return Handler


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
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(scenario))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    (directory / "workspace/keep.txt").write_text(scenario.nonce)
    (directory / "agent/settings.json").write_text(json.dumps({"compaction": {"enabled": False}, "retry": {"enabled": False}}))
    env = {
        "PATH": os.environ["PATH"], "LANG": "C.UTF-8", "HOME": str(directory / "home"), "TMPDIR": str(directory / "tmp"),
        "PI_CODING_AGENT_DIR": str(directory / "agent"), "PI_CONTEXT_TEST_URL": f"http://127.0.0.1:{server.server_port}",
        "NODE_OPTIONS": f"--import={repo}/node_modules/tsx/dist/loader.mjs", "TSX_TSCONFIG_PATH": str(repo / "tsconfig.json"),
        "PI_CONTEXT_TEST_API": "openai-responses" if name == "responses" else "openai-completions",
        "PI_NO_LOCAL_LLM": "1", "AWS_EC2_METADATA_DISABLED": "true", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    if credentials:
        for file in [directory / "workspace/keep.txt", directory / "agent/settings.json"]:
            os.chown(file, credentials["user"], credentials["group"])
            file.chmod(0o600)
    phases = 2 if name in ["resume", "isolation", "clear_resume"] else 1
    exits = []
    try:
        for phase in range(phases):
            scenario.done = False
            scenario.script = scenario.script_main(phase)
            next(scenario.script)
            session = directory / "state" / ("other.jsonl" if name == "isolation" and phase else "session.jsonl")
            command = ["node", str(repo / "packages/coding-agent/src/cli.ts"), "--mode", "json", "-p", "--session", str(session),
                       "--model", "context-test/scripted", "--system-prompt", scenario.system,
                       "-e", str(Path(__file__).with_name("provider.ts"))]
            extension = repo / "packages/coding-agent/examples/extensions/context-management/index.ts"
            # Baseline starts normally and is scored for absent advertised tools,
            # not for failure to import a file which the task asks solvers to add.
            if name != "ordinary" and extension.exists(): command += ["-e", str(extension)]
            command += [scenario.goal if phase == 0 else scenario.correction]
            proc = subprocess.Popen(command, cwd=directory / "workspace", env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, **credentials)
            try:
                stdout, stderr = proc.communicate(timeout=90)
            except subprocess.TimeoutExpired:
                scenario.errors.append("Pi did not complete the scenario")
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
            exits.append(proc.returncode)
            (directory / f"stdout-{phase}.jsonl").write_text(stdout)
            (directory / f"stderr-{phase}.txt").write_text(stderr)
            if not scenario.done or "VERIFIED-" + scenario.nonce not in stdout:
                scenario.errors.append("Required scripted trajectory did not complete")
            if proc.returncode or scenario.errors: break
        sessions = [e["id"] for e in scenario.events if e.get("type") == "session"]
        assert len(sessions) == len(exits), "Context reset created or replaced a session"
        request_sessions = {e["id"] for e in scenario.events if e.get("type") == "request_session"}
        assert request_sessions == set(sessions), "Model calls changed session identity"
        if name in ["resume", "clear_resume"] and len(sessions) == 2:
            assert sessions[0] == sessions[1], "Resume changed session identity"
        if name == "isolation" and len(sessions) == 2:
            assert sessions[0] != sessions[1], "Independent sessions share identity"
        assert (directory / "workspace/keep.txt").read_text() == scenario.nonce, "Context transition reset workspace"
        passed = not scenario.errors and len(exits) == phases and all(code == 0 for code in exits)
    except Exception as exc:
        scenario.errors.append(repr(exc))
        passed = False
    finally:
        server.shutdown()
        server.server_close()
    for filename, data in [("requests", scenario.requests), ("events", scenario.events)]:
        (directory / (filename + ".json")).write_text(json.dumps(data, ensure_ascii=True, indent=2))
    result_data = {"name": name, "passed": passed, "errors": scenario.errors, "exits": exits, "requests": len(scenario.requests), "checks": scenario.checks}
    (directory / "result.json").write_text(json.dumps(result_data, ensure_ascii=True, indent=2))
    return result_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("/workspace/pi"))
    parser.add_argument("--output", type=Path, default=Path("/logs/verifier/behavior"))
    parser.add_argument("--cases", nargs="+", choices=CASES, default=CASES)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.cases:
        try: data = run_case(name, args.repo.resolve(), args.output)
        except Exception as exc: data = {"name": name, "passed": False, "errors": [repr(exc)]}
        results.append(data)
        print(json.dumps(data, ensure_ascii=True), flush=True)
    summary = {"total": len(results), "passed": sum(r["passed"] for r in results), "external_model_calls": 0, "results": results}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if len(results) == len(args.cases) and all(r["passed"] for r in results) else 1


if __name__ == "__main__": raise SystemExit(main())
