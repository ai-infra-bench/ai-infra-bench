#!/usr/bin/env python3
"""Trusted, dependency-free behavioral assertions. Never import candidate code here."""
from __future__ import annotations

import re
import secrets


def verify(call, completed):
    def check(condition, detail):
        if not condition:
            raise AssertionError(detail)

    def success(**command):
        result = call(**command)
        check(result["error"] is None, f"{command}: unexpected error: {result['error']}")
        return result

    def construction(result, key, blocks, role):
        records = result["events"]
        check(len(records) == 1, f"expected one constructor call, observed {records}")
        event = records[0]
        check(event["event"] == "construct", f"unexpected callback: {event}")
        check(event["config"] == key, f"constructor did not receive the original config object: {event}")
        check((event["blocks"], event["groups"], event["tensors"]) == (blocks, 1, 1),
              f"resolved nonempty configuration was changed: {event}")
        check(event["role"] == role, f"constructor role changed: {event}")
        value = result["value"]
        check(value is not None and value["plugin"] and value["role"] == role,
              f"wrong connector returned: {value}")
        check(event["instance"] == value["instance"], "returned a different connector instance")
        return value["instance"]

    keys = [secrets.token_hex(12), secrets.token_hex(12)]
    blocks = [7 + secrets.randbelow(7), 23 + secrets.randbelow(7)]
    for key, count in zip(keys, blocks):
        success(op="config", key=key, blocks=count)

    # Current call forms supported by the frozen factory. No private lookup API.
    for plugin in ("Current", "Inherited", "Defaulted", "Forwarded"):
        for role in ("SCHEDULER", "WORKER"):
            for key, count in zip(keys, blocks):
                result = success(op="create", plugin=plugin, role=role, key=key)
                construction(result, key, count, role)
            completed.append(f"current/{plugin}/{role}/two-configs")

    registered = "registered_" + secrets.token_hex(8)
    success(op="register", name=registered, plugin="Inherited")
    for role in ("SCHEDULER", "WORKER"):
        result = success(op="create", plugin="Inherited", registry=registered, role=role, key=keys[1])
        construction(result, keys[1], blocks[1], role)
        completed.append(f"registered/{role}")

    # Same real worker lifecycle, no direct access to its global storage.
    result = success(op="initialize", key=keys[0])
    first = construction(result, keys[0], blocks[0], "WORKER")
    result = success(op="initialize", key=keys[0])
    check(result["events"] == [] and result["value"]["instance"] == first,
          f"repeated initialization recreated the active connector: {result}")
    completed.append("lifecycle/repeated-initialize")
    result = success(op="shutdown")
    check(result["events"] == [{"event": "shutdown", "instance": first}],
          f"shutdown did not close the active instance once: {result}")
    check(result["value"] == {"has_group": False}, "closed connector is still active")
    result = success(op="shutdown")
    check(result["events"] == [] and result["value"] == {"has_group": False},
          "repeated shutdown changed an inactive lifecycle")
    result = success(op="initialize", key=keys[1])
    second = construction(result, keys[1], blocks[1], "WORKER")
    check(second != first, "new initialization reused the closed instance")
    result = success(op="shutdown")
    check(result["events"] == [{"event": "shutdown", "instance": second}]
          and result["value"] == {"has_group": False}, "second lifecycle did not close cleanly")
    completed.append("lifecycle/shutdown-and-new-config")

    for role in ("SCHEDULER", "WORKER"):
        for kind in ("TypeError", "ValueError", "RuntimeError"):
            message = "plugin failure " + secrets.token_hex(16)
            result = call(op="create", key=keys[0], plugin="Exploding", role=role,
                          exception=kind, message=message)
            check(result["error"] == {"type": kind, "message": message},
                  f"plugin exception was swallowed or changed: {result}")
            check(len(result["events"]) == 1 and result["events"][0]["event"] == "construct"
                  and result["events"][0]["config"] == keys[0],
                  f"failing plugin was retried or received the wrong config: {result}")
            completed.append(f"plugin-exception/{role}/{kind}")
        result = call(op="create", key=keys[0], plugin="BindingError", role=role)
        error = result["error"] or {}
        check(error.get("type") == "TypeError" and "transport" in error.get("message", ""),
              f"ordinary argument-binding error was obscured: {result}")
        check(result["events"] == [], "constructor body ran despite argument-binding failure")
        completed.append(f"argument-binding/{role}")

    for role in ("SCHEDULER", "WORKER"):
        result = call(op="create", key=keys[0], plugin="Legacy", role=role)
        error = result["error"] or {}
        check(result["events"] == [], f"retired constructor body ran: {result}")
        check(bool(error.get("type")), f"old constructor was not rejected: {result}")
        message = error.get("message", "").lower()
        # Match migration concepts, not the hidden fixture name or one spelling.
        # A bare Python arity error does not tell a plugin author what to change.
        config_hint = re.search(r"kv.?cache|kv_cache_config|cache.{0,24}(config|layout)|third|3[- ]argument", message)
        action_hint = re.search(r"accept|add|pass|supply|provid|requir|updat|migrat|include|support|remov|must|expect", message)
        check(config_hint and action_hint, f"missing actionable migration guidance: {message!r}")
        completed.append(f"legacy-rejection/{role}")
        result = call(op="base_missing_config", role=role)
        check(result["error"] is not None,
              "base class still accepts the retired two-argument constructor")
        completed.append(f"base-rejects-missing-config/{role}")
