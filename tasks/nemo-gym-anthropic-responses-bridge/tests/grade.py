"""Trusted scorer; never imports candidate code. Actual HTTP in both directions."""

import argparse
import base64
import copy
import http.server
import json
import os
import queue
import secrets
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(url, body=None, headers=None):
    req = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        response = urllib.request.urlopen(req, timeout=12)
    except urllib.error.HTTPError as exc:
        response = exc
    raw = response.read()
    data = raw.decode()
    if "application/json" in response.headers.get("Content-Type", ""):
        data = json.loads(data)
    return response.status, dict(response.headers), data


def response(items, **extra):
    return {
        "id": "resp_" + secrets.token_hex(8),
        "object": "response",
        "created_at": 1,
        "model": "local-policy",
        "status": "completed",
        "output": items,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 17,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 9,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 26,
        },
        **extra,
    }


def message(text):
    return {
        "type": "message",
        "id": "msg_" + secrets.token_hex(6),
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def tool(cid, name, arguments):
    return {
        "type": "function_call",
        "call_id": cid,
        "name": name,
        "arguments": json.dumps(arguments),
        "status": "completed",
    }


def plain(content):
    if isinstance(content, str):
        return content
    return "".join(x.get("text", "") for x in content)


def image_semantics(url):
    header, payload = url.split(",", 1)
    assert header.startswith("data:") and header.endswith(";base64"), url
    return (header[5:-7].lower(), base64.b64decode(payload, validate=True))


def input_semantics(items):
    if isinstance(items, str):
        return [("text", "user", items)]
    result = []
    for x in items:
        kind = x.get("type", "message")
        if kind == "message":
            parts = x.get("content", "")
            if isinstance(parts, str):
                parts = [{"type": "input_text", "text": parts}]
            for p in parts:
                if p.get("type") in ("input_text", "output_text", "text"):
                    value = ("text", x["role"], p["text"])
                    if result and result[-1][:2] == value[:2]:
                        result[-1] = value[:2] + (result[-1][2] + value[2],)
                    else:
                        result.append(value)
                else:
                    result.append(("image", x["role"], image_semantics(p.get("image_url"))))
        elif kind == "function_call":
            result.append(("call", x["call_id"], x["name"], json.loads(x["arguments"])))
        elif kind == "function_call_output":
            result.append(("result", x["call_id"], x["output"]))
        elif kind == "reasoning":
            result.append(("reasoning", "".join(s["text"] for s in x["summary"])))
        else:
            raise AssertionError("unexpected item " + kind)
    return result


def request_semantics(payload):
    """Observe instructions without requiring a particular public field layout."""
    fragments = []
    if payload.get("instructions") is not None:
        fragments.append(payload["instructions"])
    items = payload["input"]
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    conversation = []
    for item in items:
        if item.get("type", "message") == "message" and item.get("role") in ("system", "developer"):
            assert not conversation, "instructions must precede conversation"
            content = item["content"]
            if isinstance(content, str):
                fragments.append(content)
            else:
                assert all(p["type"] in ("input_text", "text", "output_text") for p in content)
                fragments.append("\n".join(p["text"] for p in content))
        else:
            conversation.append(item)
    return "\n".join(fragments), input_semantics(conversation)


def anthropic_semantics(messages):
    result = []
    for m in messages:
        blocks = m["content"]
        if isinstance(blocks, str):
            blocks = [{"type": "text", "text": blocks}]
        for b in blocks:
            t = b["type"]
            if t == "text":
                item = ("text", m["role"], b["text"])
                if result and result[-1][:2] == item[:2]:
                    result[-1] = item[:2] + (result[-1][2] + item[2],)
                else:
                    result.append(item)
            elif t == "tool_use":
                result.append(("call", b["id"], b["name"], b["input"]))
            elif t == "tool_result":
                result.append(("result", b["tool_use_id"], plain(b["content"])))
            elif t == "thinking":
                result.append(("reasoning", b["thinking"]))
            elif t == "image":
                result.append(
                    (
                        "image",
                        m["role"],
                        image_semantics("data:"
                        + b["source"]["media_type"]
                        + ";base64,"
                        + b["source"]["data"]),
                    )
                )
            else:
                raise AssertionError("unexpected block " + t)
    return result


def parse_sse(raw):
    blocks, opened, closed = {}, set(), set()
    starts = stops = finals = 0
    envelope = None
    for frame in raw.replace("\r\n", "\n").split("\n\n"):
        lines = frame.splitlines()
        data = "\n".join(x[5:].lstrip() for x in lines if x.startswith("data:"))
        if not data:
            continue
        event = json.loads(data)
        named = [x[6:].strip() for x in lines if x.startswith("event:")]
        assert not named or named == [event["type"]], event
        t = event["type"]
        if t == "ping":
            continue
        assert stops == 0, "event after message_stop"
        if t == "message_start":
            starts += 1
            assert starts == 1 and not opened
            envelope = copy.deepcopy(event["message"])
            assert envelope["type"] == "message" and envelope["content"] == []
        else:
            assert starts == 1, "event before message_start"
        if t == "content_block_start":
            i = event["index"]
            assert i not in opened
            opened.add(i)
            blocks[i] = copy.deepcopy(event["content_block"])
            if blocks[i]["type"] == "tool_use":
                blocks[i]["_arguments"] = ""
        elif t == "content_block_delta":
            i = event["index"]
            assert i in opened and i not in closed
            b = blocks[i]
            d = event["delta"]
            dt = d["type"]
            if dt == "text_delta":
                assert b["type"] == "text"
                b["text"] += d["text"]
            elif dt == "thinking_delta":
                assert b["type"] == "thinking"
                b["thinking"] += d["thinking"]
            elif dt == "signature_delta":
                assert b["type"] == "thinking"
                b["signature"] = b.get("signature", "") + d["signature"]
            elif dt == "input_json_delta":
                assert b["type"] == "tool_use"
                b["_arguments"] += d["partial_json"]
            else:
                raise AssertionError("unknown delta " + dt)
        elif t == "content_block_stop":
            i = event["index"]
            assert i in opened and i not in closed
            closed.add(i)
        elif t == "message_delta":
            finals += 1
            assert opened == closed
            envelope.update(event["delta"])
            envelope["usage"].update(event.get("usage", {}))
        elif t == "message_stop":
            stops += 1
            assert opened == closed and finals >= 1
        elif t not in ("message_start", "content_block_start"):
            raise AssertionError("unexpected SSE event " + t)
    assert starts == stops == 1 and finals >= 1
    assert sorted(blocks) == list(range(len(blocks)))
    for i in sorted(blocks):
        b = blocks[i]
        if b["type"] == "tool_use":
            raw_args = b.pop("_arguments")
            if raw_args:
                b["input"] = json.loads(raw_args)
        envelope["content"].append(b)
    return envelope


class Backend(http.server.BaseHTTPRequestHandler):
    records = queue.Queue()
    payload = response([message("initial")])
    status = 200

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.records.put((self.path, data))
        if self.path.endswith("/chat/completions"):
            value = {
                "id": "chat_" + secrets.token_hex(5),
                "object": "chat.completion",
                "created": 1,
                "model": "local-policy",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": data["messages"][-1]["content"],
                        },
                    }
                ],
            }
        else:
            value = type(self).payload
        raw = json.dumps(value).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--python", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--candidate-user")
    p.add_argument(
        "--fixture", default=str(Path(__file__).with_name("serve_candidate.py"))
    )
    args = p.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    records = []
    processes = []
    logs = []
    backend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    backend_url = f"http://127.0.0.1:{backend.server_port}"

    def start(mode):
        port = free_port()
        cmd = [
            args.python,
            args.fixture,
            "--repo",
            args.repo,
            "--backend",
            backend_url,
            "--port",
            str(port),
            "--mode",
            mode,
        ]
        if args.candidate_user:
            cmd = ["runuser", "-u", args.candidate_user, "--", *cmd]
        log = (out / f"{mode}-server.log").open("w")
        logs.append(log)
        env = dict(
            os.environ,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=str(Path(args.repo).resolve()),
        )
        proc = subprocess.Popen(
            cmd,
            cwd=args.repo,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        processes.append(proc)
        url = f"http://127.0.0.1:{port}"
        for _ in range(200):
            if proc.poll() is not None:
                raise AssertionError(
                    f"candidate exited during startup: {proc.returncode}"
                )
            try:
                if call(url + "/probe-ready")[0] == 200:
                    return url
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.05)
        raise AssertionError("candidate startup deadline exceeded")

    def check(name, fn):
        t = time.monotonic()
        try:
            fn()
            records.append(
                {"name": name, "passed": True, "seconds": time.monotonic() - t}
            )
        except Exception as exc:
            records.append(
                {
                    "name": name,
                    "passed": False,
                    "error": str(exc),
                    "seconds": time.monotonic() - t,
                }
            )

    def ok(url, data):
        status, _, result = call(url, data)
        assert status == 200, (status, result)
        return result

    def bad(url, data):
        status, _, result = call(url, data)
        assert 400 <= status < 600, (status, result)
        assert result, "missing error detail"

    def clean_records():
        while not Backend.records.empty():
            Backend.records.get_nowait()

    def seen():
        return Backend.records.get(timeout=3)[1]

    def set_output(value):
        Backend.payload = value
        Backend.status = 200
        clean_records()

    try:
        native = start("native")
        request_url = start("request")
        override = start("override")
        api = native + "/public-converter/"
        text = '中文\n"quoted"\\x 😀 ' + secrets.token_hex(12)
        cid1, cid2 = "call_" + secrets.token_hex(8), "call_" + secrets.token_hex(8)
        name = "lookup_" + secrets.token_hex(4)
        schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "flags": {"type": "array", "items": {"type": "boolean"}},
            },
            "required": ["path"],
        }
        arguments = {
            "path": text,
            "flags": [True, False],
            "nested": {"n": 0, "empty": ""},
        }
        a_request = {
            "model": "public-policy",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": text}],
        }
        tools = [{"name": name, "description": text, "input_schema": schema}]

        def text_route():
            set_output(response([message(text)]))
            value = ok(native + "/v1/messages", a_request)
            assert (
                value["role"] == "assistant"
                and value["type"] == "message"
                and value["id"]
            )
            assert (
                plain(value["content"]) == text and value["stop_reason"] == "end_turn"
            )
            assert (
                value["usage"]["input_tokens"] == 17
                and value["usage"]["output_tokens"] == 9
            )
            assert input_semantics(seen()["input"]) == [("text", "user", text)]

        check("messages_native_model_http", text_route)

        def instructions():
            data = a_request | {
                "system": [
                    {"type": "text", "text": "one " + text},
                    {"type": "text", "text": "two"},
                ],
                "temperature": 0,
                "top_p": 0.7,
                "tools": tools,
            }
            value = ok(api + "ingress-request", data)
            assert request_semantics(value) == ("one " + text + "\ntwo", [("text", "user", text)])
            assert (
                value["temperature"] == 0
                and value["top_p"] == 0.7
                and value["max_output_tokens"] == 128
            )
            assert (
                value["tools"][0]["name"] == name
                and value["tools"][0]["parameters"] == schema
            )
            assert value["tools"][0]["description"] == text

        check("ingress_instructions_sampling_schema", instructions)

        def forwarded_fields():
            # Observe the actual downstream HTTP payload, not a converter helper.
            for url in (native, request_url):
                for stream in (False, True):
                    for selection, expected_choice in [
                        ({"type": "auto"}, "auto"),
                        ({"type": "none"}, "none"),
                        ({"type": "any"}, "required"),
                        ({"type": "tool", "name": name}, {"type": "function", "name": name}),
                    ]:
                        set_output(response([message(text)]))
                        body = a_request | {
                            "system": [{"type": "text", "text": text}, {"type": "text", "text": "next"}],
                            "tools": tools,
                            "tool_choice": selection,
                            "temperature": 0,
                            "top_p": 0.6,
                            "max_tokens": 57,
                            "stream": stream,
                        }
                        status, _, reply = call(url + "/v1/messages", body)
                        assert status == 200, (status, reply)
                        if stream:
                            reply = parse_sse(reply)
                        assert plain(reply["content"]) == text
                        payload = seen()
                        assert request_semantics(payload) == (text + "\nnext", [("text", "user", text)]), payload
                        assert payload.get("max_output_tokens") == 57, payload
                        assert payload.get("temperature") == 0 and payload.get("top_p") == 0.6, payload
                        assert payload.get("tool_choice") == expected_choice, payload
                        assert payload.get("stream") in (None, False), payload
                        assert len(payload.get("tools", [])) == 1, payload
                        mapped = payload["tools"][0]
                        assert mapped["type"] == "function" and mapped["name"] == name, mapped
                        assert mapped["description"] == text and mapped["parameters"] == schema, mapped

        check("messages_forward_fields_to_actual_backend", forwarded_fields)

        def choices():
            for a, r in [
                ({"type": "auto"}, "auto"),
                ({"type": "none"}, "none"),
                ({"type": "any"}, "required"),
                ({"type": "tool", "name": name}, {"type": "function", "name": name}),
            ]:
                assert (
                    ok(
                        api + "ingress-request",
                        a_request | {"tools": tools, "tool_choice": a},
                    )["tool_choice"]
                    == r
                )
                body = {
                    "input": text,
                    "tools": [
                        {
                            "type": "function",
                            "name": name,
                            "parameters": schema,
                            "strict": False,
                        }
                    ],
                    "tool_choice": r,
                }
                # Explicit mapped choices override conflicting backend extras.
                for extras in ({}, {"tool_choice": {"type": "none"}}):
                    request_value = ok(api + "egress-request", {"body": body, "extra_body": extras})
                    # With tools present, an omitted choice means auto. Explicit
                    # null or malformed values are not equivalent to omission.
                    actual_choice = request_value.get("tool_choice", {"type": "auto"})
                    assert isinstance(actual_choice, dict), actual_choice
                    assert actual_choice.get("type") == a["type"], actual_choice
                    if "name" in a:
                        assert actual_choice.get("name") == a["name"], actual_choice
                    # Omitting this optional flag and explicitly allowing parallel
                    # calls express the same default request behavior.
                    assert actual_choice.get("disable_parallel_tool_use", False) is False, actual_choice

        check("tool_selection_both_directions", choices)
        history = [
            {"role": "user", "content": text},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "before"},
                    {"type": "tool_use", "id": cid1, "name": name, "input": arguments},
                    {"type": "text", "text": "between"},
                    {"type": "tool_use", "id": cid2, "name": name, "input": {}},
                    {"type": "text", "text": "after"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": cid2, "content": "second"},
                    {"type": "tool_result", "tool_use_id": cid1, "content": "first"},
                    {"type": "text", "text": "continue"},
                ],
            },
        ]
        expected = anthropic_semantics(history)

        def ingress_history():
            converted = ok(api + "ingress-request", a_request | {"messages": history})
            assert input_semantics(converted["input"]) == expected

        check("ingress_interleaved_parallel_tool_history", ingress_history)
        r_items = [
            {"role": "user", "content": text},
            tool(cid1, name, arguments),
            tool(cid2, name, {}),
            {"type": "function_call_output", "call_id": cid2, "output": "second"},
            {"type": "function_call_output", "call_id": cid1, "output": "first"},
            {"role": "user", "content": "continue"},
        ]

        def egress_history():
            body = {
                "input": [
                    {"role": "system", "content": "first"},
                    {"role": "developer", "content": "second"},
                    *r_items,
                ],
                "instructions": "top",
                "max_output_tokens": 72,
                "temperature": 0,
                "top_p": 0.8,
                "tools": [
                    {
                        "type": "function",
                        "name": name,
                        "description": text,
                        "parameters": schema,
                        "strict": False,
                    }
                ],
            }
            value = ok(
                api + "egress-request",
                {
                    "body": body,
                    "model": "chosen-model",
                    "max_tokens": 999,
                    "extra_body": {"model": "wrong"},
                },
            )
            assert value["model"] == "chosen-model" and value["max_tokens"] == 72
            system = value["system"]
            if not isinstance(system, str):
                assert all(block["type"] == "text" for block in system)
                system = "\n".join(block["text"] for block in system)
            assert system == "top\nfirst\nsecond", system
            assert anthropic_semantics(value["messages"]) == input_semantics(r_items)
            assert value["temperature"] == 0 and value["top_p"] == 0.8
            assert (
                value["tools"][0]["input_schema"] == schema
                and value["tools"][0]["description"] == text
            )
            assert (
                ok(api + "egress-request", {"body": {"input": text}, "max_tokens": 91})[
                    "max_tokens"
                ]
                == 91
            )

        check("egress_requests_and_defaults", egress_history)

        def system_fragments():
            fragments = ["first " + text, "", "last"]
            data = a_request | {"system": [{"type": "text", "text": t} for t in fragments]}
            assert request_semantics(ok(api + "ingress-request", data)) == ("\n".join(fragments), [("text", "user", text)])
            for url in (native, request_url):
                for stream in (False, True):
                    set_output(response([message(text)]))
                    status, _, reply = call(url + "/v1/messages", data | {"stream": stream})
                    assert status == 200, (status, reply)
                    assert request_semantics(seen()) == ("\n".join(fragments), [("text", "user", text)])
            converted = ok(api + "egress-request", {"body": {"instructions": fragments[0], "input": [
                {"role": "system", "content": ""}, {"role": "developer", "content": "last"}, {"role": "user", "content": text}]}})
            system = converted["system"]
            assert (system if isinstance(system, str) else "\n".join(b["text"] for b in system)) == "\n".join(fragments)

            # Empty fragments still contribute a separator. Observe semantic
            # text, allowing either a system string or differently grouped blocks.
            for role in ("system", "developer"):
                other_role = "developer" if role == "system" else "system"
                cases = (
                    ("empty_instructions", {"instructions": ""}, [(role, "tail")], "\ntail"),
                    ("empty_message_first", {}, [(role, ""), (other_role, "tail")], "\ntail"),
                    ("empty_message_middle", {"instructions": "head"}, [(role, ""), (other_role, "tail")], "head\n\ntail"),
                    ("empty_message_last", {"instructions": "head"}, [(role, "")], "head\n"),
                )
                for label, fields, leading, expected in cases:
                    for block_content in (False, True):
                        items = [
                            {"role": r, "content": [{"type": "input_text", "text": t}] if block_content else t}
                            for r, t in leading
                        ]
                        body = fields | {"input": items + [{"role": "user", "content": text}]}
                        converted = ok(api + "egress-request", {"body": body})
                        system = converted.get("system")
                        if isinstance(system, str):
                            actual = system
                        else:
                            assert isinstance(system, list), (label, role, block_content, system)
                            assert all(b.get("type") == "text" and isinstance(b.get("text"), str) for b in system)
                            actual = "\n".join(b["text"] for b in system)
                        assert actual == expected, (label, role, block_content, expected, actual)
                        assert anthropic_semantics(converted["messages"]) == [("text", "user", text)]

        check("system_empty_fragments_both_directions", system_fragments)

        def invalid_system():
            for block in ({"type": "image", "source": {"type": "url", "url": "https://example.com/a.png"}}, {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text}}):
                data = a_request | {"system": [{"type": "text", "text": text}, block]}
                bad(api + "ingress-request", data)
                for url in (native, request_url):
                    for stream in (False, True):
                        clean_records()
                        bad(url + "/v1/messages", data | {"stream": stream})

        check("unsupported_system_is_explicit_error", invalid_system)

        def extra_tools():
            mapped = {"type": "function", "name": name, "description": text, "parameters": schema, "strict": False}
            unwanted = {"name": "unwanted", "input_schema": {"type": "object", "properties": {}}}
            for extras in ({}, {"tools": [unwanted]}):
                value = ok(api + "egress-request", {"body": {"input": text, "tools": []}, "extra_body": extras})
                assert not value.get("tools"), value
                value = ok(api + "egress-request", {"body": {"input": text, "tools": [mapped]}, "extra_body": extras})
                assert len(value["tools"]) == 1 and value["tools"][0]["name"] == name, value
                assert value["tools"][0]["input_schema"] == schema, value

        check("explicit_tools_override_extra_body", extra_tools)

        def results_list():
            data = a_request | {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": cid1,
                                "content": [
                                    {"type": "text", "text": "a"},
                                    {"type": "text", "text": "b"},
                                ],
                                "is_error": False,
                            }
                        ],
                    }
                ]
            }
            assert ok(api + "ingress-request", data)["input"][0]["output"] == "a\nb"

        check("text_block_tool_result", results_list)

        def images():
            fixtures = json.loads((Path(__file__).parent / "fixtures/images.json").read_text())
            for mime in ["image/png", "image/jpeg", "image/gif", "image/webp"]:
                b64 = fixtures[mime]
                block = {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}
                for caption in ([], [{"type": "text", "text": text}]):
                    ar = a_request | {"messages": [{"role": "user", "content": caption + [block]}]}
                    expected = anthropic_semantics(ar["messages"])
                    value = ok(api + "ingress-request", ar)
                    assert input_semantics(value["input"]) == expected
                    parts = ([{"type": "input_text", "text": text}] if caption else []) + [
                        {"type": "input_image", "image_url": "data:" + mime + ";base64," + b64, "detail": "auto"}
                    ]
                    reverse = ok(api + "egress-request", {"body": {"input": [{"role": "user", "content": parts}]}})
                    assert anthropic_semantics(reverse["messages"]) == expected
                    for streaming in (False, True):
                        set_output(response([message(text)]))
                        status, _, reply = call(native + "/v1/messages", ar | {"stream": streaming})
                        assert status == 200, (mime, bool(caption), streaming, status, reply)
                        assert input_semantics(seen()["input"]) == expected

            # Interleave images with text so text-first/image-last partitioning
            # cannot pass. Consecutive same-role message grouping is immaterial.
            image_urls = [
                "data:image/png;base64," + fixtures["image/png"],
                "data:image/png;base64," + fixtures["alternate_png"],
            ]
            blocks = []
            parts = []
            for image_url, caption in zip(image_urls, ("between " + text, "after " + text)):
                blocks.extend([
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_url.split(",", 1)[1]}},
                    {"type": "text", "text": caption},
                ])
                parts.extend([
                    {"type": "input_image", "image_url": image_url, "detail": "auto"},
                    {"type": "input_text", "text": caption},
                ])
            messages = [{"role": "user", "content": blocks}]
            expected = anthropic_semantics(messages)
            forward = ok(api + "ingress-request", a_request | {"messages": messages})
            assert input_semantics(forward["input"]) == expected, forward
            reverse = ok(api + "egress-request", {"body": {"input": [{"role": "user", "content": parts}]}})
            assert anthropic_semantics(reverse["messages"]) == expected, reverse

        check("base64_image_transport_both_directions", images)
        outputs = [
            {
                "type": "reasoning",
                "id": "rs_one",
                "summary": [{"type": "summary_text", "text": "think " + text}],
            },
            message("before"),
            tool(cid1, name, arguments),
            message("after"),
        ]

        def output_conversion():
            result = ok(api + "ingress-response", {"response": response(outputs)})
            assert anthropic_semantics(
                [{"role": "assistant", "content": result["content"]}]
            ) == input_semantics(outputs)
            source = {
                "id": "msg_x",
                "type": "message",
                "role": "assistant",
                "model": "x",
                "content": result["content"],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 17, "output_tokens": 9},
            }
            reverse = ok(api + "egress-response", {"response": source})
            assert input_semantics(reverse["output"]) == input_semantics(outputs)
            assert reverse["id"] and reverse["object"] == "response"

        check("response_order_reasoning_and_tools", output_conversion)

        def reasoning_history():
            a = a_request | {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": text, "signature": ""},
                            {"type": "text", "text": "answer"},
                        ],
                    }
                ]
            }
            got = ok(api + "ingress-request", a)
            assert input_semantics(got["input"]) == [
                ("reasoning", text),
                ("text", "assistant", "answer"),
            ]
            r = {
                "input": [
                    {
                        "type": "reasoning",
                        "id": "rs_history",
                        "summary": [{"type": "summary_text", "text": text}],
                    },
                    {"role": "assistant", "content": "answer"},
                ]
            }
            assert anthropic_semantics(
                ok(api + "egress-request", {"body": r})["messages"]
            ) == [("reasoning", text), ("text", "assistant", "answer")]

            # Plain reasoning can occur between visible text blocks. Preserve
            # that boundary in both Anthropic-to-Responses public conversions.
            before_text, thinking_text, after_text = "before " + text, "reason " + text, "after " + text
            blocks = [
                {"type": "text", "text": before_text},
                {"type": "thinking", "thinking": thinking_text, "signature": ""},
                {"type": "text", "text": after_text},
            ]
            expected = [("text", "assistant", before_text), ("reasoning", thinking_text), ("text", "assistant", after_text)]
            request_value = ok(api + "ingress-request", a_request | {"messages": [{"role": "assistant", "content": blocks}]})
            assert input_semantics(request_value["input"]) == expected
            response_value = ok(api + "egress-response", {"response": {
                "id": "msg_middle_reasoning", "type": "message", "role": "assistant", "model": "local-policy",
                "content": blocks, "stop_reason": "end_turn", "usage": {"input_tokens": 17, "output_tokens": 9},
            }})
            assert input_semantics(response_value["output"]) == expected

        check("plain_reasoning_history_both_directions", reasoning_history)

        def stops_and_cache():
            for a, r in [
                ("end_turn", None),
                ("tool_use", None),
                ("max_tokens", "max_output_tokens"),
                ("refusal", "content_filter"),
            ]:
                content = (
                    [{"type": "tool_use", "id": cid1, "name": name, "input": arguments}]
                    if a == "tool_use"
                    else [{"type": "text", "text": text}]
                )
                value = ok(
                    api + "egress-response",
                    {
                        "response": {
                            "id": "msg_" + cid1,
                            "type": "message",
                            "role": "assistant",
                            "model": "x",
                            "content": content,
                            "stop_reason": a,
                            "usage": {
                                "input_tokens": 17,
                                "cache_read_input_tokens": 5,
                                "output_tokens": 9,
                            },
                        }
                    },
                )
                assert (value.get("incomplete_details") or {}).get("reason") == r
                assert (
                    value["usage"]["input_tokens"] == 22
                    and value["usage"]["input_tokens_details"]["cached_tokens"] == 5
                    and value["usage"]["total_tokens"] == 31
                )
                back = ok(api + "ingress-response", {"response": value})
                assert back["stop_reason"] == a
                assert (
                    back["usage"]["input_tokens"] == 17
                    and back["usage"]["cache_read_input_tokens"] == 5
                )

        check("termination_and_cache_accounting", stops_and_cache)

        def native_refusal():
            refused = response([message(text) | {"content": [
                {"type": "output_text", "text": "preface: ", "annotations": []},
                {"type": "refusal", "refusal": text},
            ]}])
            direct = ok(api + "ingress-response", {"response": refused})
            assert direct["stop_reason"] == "refusal", direct
            assert plain(direct["content"]) == "preface: " + text
            for url in (native, request_url):
                for stream in (False, True):
                    set_output(refused)
                    status, _, reply = call(url + "/v1/messages", a_request | {"stream": stream})
                    assert status == 200, (status, reply)
                    if stream:
                        reply = parse_sse(reply)
                    assert reply["stop_reason"] == "refusal", reply
                    assert plain(reply["content"]) == "preface: " + text
                    assert reply["usage"]["input_tokens"] == 17 and reply["usage"]["output_tokens"] == 9
                    seen()

        check("native_responses_refusal_http_and_sse", native_refusal)

        def streaming():
            set_output(response(outputs))
            code, headers, raw = call(
                native + "/v1/messages", a_request | {"stream": True}
            )
            assert code == 200 and "text/event-stream" in headers.get(
                "content-type", headers.get("Content-Type", "")
            ), (code, raw)
            value = parse_sse(raw)
            assert anthropic_semantics(
                [{"role": "assistant", "content": value["content"]}]
            ) == input_semantics(outputs)
            assert (
                value["stop_reason"] == "tool_use"
                and value["usage"]["output_tokens"] == 9
            )
            assert seen().get("stream") in (None, False)
            complete = ok(api + "ingress-response", {"response": response(outputs)})
            status, _, direct_raw = call(api + "sse", complete)
            assert status == 200
            direct = parse_sse(direct_raw)
            assert anthropic_semantics(
                [{"role": "assistant", "content": direct["content"]}]
            ) == input_semantics(outputs)
            assert direct["stop_reason"] == "tool_use"
            # Real pinned SDK also consumes this HTTP stream and assembles tool inputs.
            from anthropic import Anthropic

            with Anthropic(
                api_key="local", base_url=native, max_retries=0
            ).messages.stream(**a_request) as stream:
                final = stream.get_final_message()
            assert final.stop_reason == "tool_use"
            assert anthropic_semantics(
                [
                    {
                        "role": "assistant",
                        "content": [x.model_dump() for x in final.content],
                    }
                ]
            ) == input_semantics(outputs)

            # Cache-read input tokens must survive actual HTTP SSE assembly,
            # with the same usage semantics as the non-streaming Messages reply.
            for cached_tokens in (5, 0):
                backend_usage = {
                    "input_tokens": 22,
                    "input_tokens_details": {"cached_tokens": cached_tokens},
                    "output_tokens": 9,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 31,
                }
                expected_usage = (22 - cached_tokens, cached_tokens, 9)
                for url in (native, request_url):
                    observed_usage = []
                    with Anthropic(api_key="local", base_url=url, max_retries=0) as client:
                        for streaming_mode in (False, True):
                            set_output(response([message(text)], usage=backend_usage))
                            if streaming_mode:
                                with client.messages.stream(**a_request) as stream:
                                    reply = stream.get_final_message()
                            else:
                                reply = client.messages.create(**a_request)
                            # The optional Messages cache count may be absent/None
                            # when zero; do not force an Oracle-specific layout.
                            cached = getattr(reply.usage, "cache_read_input_tokens", None)
                            actual = (reply.usage.input_tokens, 0 if cached is None else cached, reply.usage.output_tokens)
                            assert actual == expected_usage, (url, streaming_mode, cached_tokens, expected_usage, actual)
                            assert reply.stop_reason == "end_turn"
                            assert anthropic_semantics([{"role": "assistant", "content": [b.model_dump() for b in reply.content]}]) == [("text", "assistant", text)]
                            assert seen().get("stream") in (None, False)
                            observed_usage.append(actual)
                    assert observed_usage[0] == observed_usage[1]

        check("messages_sse_and_real_sdk", streaming)

        def multiround():
            history = [{"role": "user", "content": text}]
            for n in range(3):
                cid = "tool_" + secrets.token_hex(8)
                set_output(response([tool(cid, name, {"round": n, "text": text})]))
                reply = ok(native + "/v1/messages", a_request | {"messages": history})
                assert reply["content"][0]["input"] == {"round": n, "text": text}
                assert reply["content"][0]["id"] == cid
                history.extend(
                    [
                        {"role": "assistant", "content": reply["content"]},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": cid,
                                    "content": f"result-{n}",
                                }
                            ],
                        },
                    ]
                )
                seen()
            set_output(response([message("final " + text)]))
            reply = ok(native + "/v1/messages", a_request | {"messages": history})
            assert plain(reply["content"]) == "final " + text
            assert input_semantics(seen()["input"]) == anthropic_semantics(history)

        check("three_tool_rounds_and_final_answer", multiround)

        def sessions():
            set_output(response([message(text)]))
            trace = secrets.token_hex(12)
            status, headers, _ = call(
                request_url + "/v1/messages", a_request, {"x-bridge-trace": trace}
            )
            assert status == 200
            witness = seen()["request_witness"]
            assert witness["trace"] == trace and witness["session"]
            cookie = headers.get("set-cookie", headers.get("Set-Cookie"))
            assert cookie
            call(
                request_url + "/v1/messages",
                a_request,
                {"x-bridge-trace": "next", "Cookie": cookie.split(";")[0]},
            )
            assert seen()["request_witness"]["session"] == witness["session"]
            assert ok(override + "/v1/messages", a_request) == {
                "custom_messages_handler": "public-policy"
            }

        check("request_session_and_subclass_override", sessions)

        def existing_routes():
            set_output(response([message(text)]))
            assert (
                ok(native + "/v1/responses", {"input": text})["output"][0]["content"][
                    0
                ]["text"]
                == text
            )
            assert (
                ok(
                    native + "/v1/chat/completions",
                    {"model": "x", "messages": [{"role": "user", "content": text}]},
                )["choices"][0]["message"]["content"]
                == text
            )

        check("existing_responses_chat_routes", existing_routes)

        def empty_and_isolation():
            # A bare Responses input string is a user message, including when
            # empty; checking only options/tools on this path misses text loss.
            for bare_text in ("", text):
                value = ok(api + "egress-request", {"body": {"input": bare_text}})
                assert anthropic_semantics(value["messages"]) == [("text", "user", bare_text)], value

            # An empty string is still text. Exercise both public request
            # directions with string and text-block input representations.
            for role in ("user", "assistant"):
                expected = [("text", role, "")]
                for content in ("", [{"type": "text", "text": ""}]):
                    value = ok(api + "ingress-request", a_request | {"messages": [{"role": role, "content": content}]})
                    assert input_semantics(value["input"]) == expected, (role, content, value)
                for content in ("", [{"type": "input_text", "text": ""}]):
                    value = ok(api + "egress-request", {"body": {"input": [{"role": role, "content": content}]}})
                    assert anthropic_semantics(value["messages"]) == expected, (role, content, value)

            # The pinned EasyInputMessage schema uses input_text for assistant
            # content too; exercise nonempty text independently of empty handling.
            value = ok(api + "egress-request", {"body": {"input": [{"role": "assistant", "content": [{"type": "input_text", "text": text}]}]}})
            assert anthropic_semantics(value["messages"]) == [("text", "assistant", text)], value

            # Empty visible output remains observable on its own and after a
            # tool boundary; adjacent plain text grouping remains unrestricted.
            for after_tool in (False, True):
                outputs = ([tool(cid1, name, arguments)] if after_tool else []) + [message("")]
                blocks = ([{"type": "tool_use", "id": cid1, "name": name, "input": arguments}] if after_tool else []) + [{"type": "text", "text": ""}]
                expected = input_semantics(outputs)
                forward = ok(api + "ingress-response", {"response": response(outputs)})
                assert anthropic_semantics([{"role": "assistant", "content": forward["content"]}]) == expected, forward
                reverse = ok(api + "egress-response", {"response": {
                    "id": "msg_empty_output", "type": "message", "role": "assistant", "model": "local-policy",
                    "content": blocks, "stop_reason": "tool_use" if after_tool else "end_turn",
                    "usage": {"input_tokens": 17, "output_tokens": 9},
                }})
                assert input_semantics(reverse["output"]) == expected, reverse

            assert input_semantics(
                ok(
                    api + "ingress-request",
                    a_request | {"messages": [{"role": "user", "content": ""}]},
                )["input"]
            ) == [("text", "user", "")]
            from concurrent.futures import ThreadPoolExecutor

            texts = [secrets.token_hex(20) for _ in range(12)]

            def go(t):
                return input_semantics(
                    ok(
                        api + "ingress-request",
                        a_request | {"messages": [{"role": "user", "content": t}]},
                    )["input"]
                )

            with ThreadPoolExecutor(max_workers=4) as pool:
                assert list(pool.map(go, texts)) == [
                    [("text", "user", t)] for t in texts
                ]

        check("empty_text_and_concurrent_conversion_isolation", empty_and_isolation)
        for label, block in [
            (
                "unsupported_content",
                {
                    "type": "server_tool_use",
                    "id": "srv",
                    "name": "web_search",
                    "input": {},
                },
            ),
            (
                "remote_image",
                {
                    "type": "image",
                    "source": {"type": "url", "url": "https://example.com/a.png"},
                },
            ),
            (
                "invalid_base64",
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "%%%",
                    },
                },
            ),
            (
                "error_tool_result",
                {
                    "type": "tool_result",
                    "tool_use_id": cid1,
                    "content": "failed",
                    "is_error": True,
                },
            ),
        ]:
            def reject_unsupported(block=block, label=label):
                # A preceding valid text block must not bypass image validation.
                prefixes = ([], [{"type": "text", "text": text}]) if label == "invalid_base64" else ([],)
                for prefix in prefixes:
                    data = a_request | {"messages": [{"role": "user", "content": prefix + [block]}]}
                    bad(api + "ingress-request", data)
                    for streaming in (False, True):
                        bad(native + "/v1/messages", data | {"stream": streaming})
            check(label, reject_unsupported)

        def invalid_egress():
            for block in [
                {"type": "tool_use", "id": cid1, "name": name, "input": [1, 2]},
                {
                    "type": "tool_use",
                    "id": cid1,
                    "name": name,
                    "input": "not an object",
                },
            ]:
                bad(
                    api + "ingress-request",
                    a_request
                    | {"messages": [{"role": "assistant", "content": [block]}]},
                )
                bad(
                    api + "egress-response",
                    {
                        "response": {
                            "id": "msg_invalid",
                            "type": "message",
                            "role": "assistant",
                            "model": "local-policy",
                            "content": [block],
                            "stop_reason": "tool_use",
                            "usage": {"input_tokens": 1, "output_tokens": 1},
                        }
                    },
                )
            hosted = a_request | {
                "tools": [{"type": "web_search_20250305", "name": "web_search"}]
            }
            bad(api + "ingress-request", hosted)
            bad(native + "/v1/messages", hosted | {"stream": True})
            for value in ["", " ", "null", "[1,2]", "{invalid"]:
                invalid_call = tool(cid1, name, {}) | {"arguments": value}
                bad(
                    api + "egress-request",
                    {"body": {"input": [invalid_call]}},
                )
                invalid_response = response([invalid_call])
                bad(api + "ingress-response", {"response": invalid_response})
                for stream in (False, True):
                    set_output(invalid_response)
                    bad(native + "/v1/messages", a_request | {"stream": stream})
            # These spellings are accepted by Python's default json.loads but
            # are not JSON numbers, including when nested inside an object.
            for value in (
                '{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}',
                '{"x": [NaN]}', '{"outer": {"x": Infinity}}',
                '{"outer": [{"x": -Infinity}]}',
            ):
                invalid_call = tool(cid1, name, {}) | {"arguments": value}
                invalid_response = response([invalid_call])
                for operation, payload in (
                    ("egress-request", {"body": {"input": [invalid_call]}}),
                    ("ingress-response", {"response": invalid_response}),
                ):
                    # Observe the public call before a web serializer could
                    # reject or turn a non-finite value into null for it.
                    status, _, returned = call(api + operation, payload | {"observe_return": True})
                    assert 400 <= status < 600, (operation, value, status, returned)
                    bad(api + operation, payload)
                for url in (native, request_url):
                    for stream in (False, True):
                        set_output(invalid_response)
                        status, _, reply = call(url + "/v1/messages", a_request | {"stream": stream})
                        assert 400 <= status < 600, (url, value, stream, status, reply)
            # Rejecting token spellings must not reject ordinary JSON strings,
            # object keys, finite numbers, booleans, null, or an empty object.
            for arguments in (
                {},
                {"NaN": "Infinity", "text": "NaN Infinity -Infinity", "nested": [{"x": "NaN"}]},
                {"numbers": [0, -2, 1.25, 1e-6], "flags": [True, False, None]},
            ):
                valid_call = tool(cid1, name, arguments)
                valid_response_body = response([valid_call])
                request_payload = {"body": {"input": [valid_call]}}
                response_payload = {"response": valid_response_body}
                for operation, payload in (
                    ("egress-request", request_payload), ("ingress-response", response_payload),
                ):
                    assert ok(api + operation, payload | {"observe_return": True}) == {"returned": True}
                valid_request = ok(api + "egress-request", request_payload)
                assert anthropic_semantics(valid_request["messages"]) == [("call", cid1, name, arguments)]
                valid_response = ok(api + "ingress-response", response_payload)
                assert valid_response["content"][0]["input"] == arguments
                for url in (native, request_url):
                    for stream in (False, True):
                        set_output(valid_response_body)
                        status, _, reply = call(url + "/v1/messages", a_request | {"stream": stream})
                        assert status == 200, (url, arguments, stream, status, reply)
                        if stream:
                            reply = parse_sse(reply)
                        assert reply["content"][0]["input"] == arguments
            bad(
                api + "egress-request",
                {"body": {"input": text, "tools": [{"type": "web_search_preview"}]}},
            )
            bad(
                api + "egress-response",
                {"response": {"content": [{"type": "not_supported"}]}},
            )

        check("invalid_arguments_and_unsupported_egress", invalid_egress)

        def backend_failures():
            failed = response(
                [],
                status="failed",
                error={"code": "server_error", "message": "backend failed"},
            )
            bad(api + "ingress-response", {"response": failed})
            set_output(failed)
            bad(native + "/v1/messages", a_request | {"stream": True})
            set_output({"error": {"message": "upstream unavailable"}})
            Backend.status = 503
            assert call(request_url + "/v1/messages", a_request)[0] == 503
            Backend.status = 200

        check("failed_backend_not_success_and_http_status", backend_failures)

        def native_backend_status():
            try:
                # Non-retryable responses exercise the actual OpenAI backend
                # without changing the backend's retry policy for this task.
                for expected in (400, 422):
                    for streaming in (False, True):
                        set_output({"error": {"message": "upstream rejected input"}})
                        Backend.status = expected
                        status, _, reply = call(native + "/v1/messages", a_request | {"stream": streaming})
                        assert status == expected, (expected, streaming, status, reply)
            finally:
                Backend.status = 200
        check("native_backend_http_status", native_backend_status)

    except Exception as exc:
        records.append(
            {"name": "environment_or_startup", "passed": False, "error": str(exc)}
        )
    finally:
        for proc in processes:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        backend.shutdown()
        for log in logs:
            log.close()
    # Fail closed: zero checks or an early child exit can never earn reward.
    expected_count = 27
    passed = sum(x["passed"] for x in records)
    success = len(records) == expected_count and passed == expected_count
    summary = {
        "reward": int(success),
        "passed": passed,
        "total": len(records),
        "required": expected_count,
        "cases": records,
        "scope": "real loopback HTTP, candidate child process, fixed SDK; container identity recorded separately",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    (out / "reward.txt").write_text(str(int(success)) + "\n")
    print(
        json.dumps(
            {
                "reward": int(success),
                "passed": passed,
                "total": len(records),
                "failed": [x for x in records if not x["passed"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
