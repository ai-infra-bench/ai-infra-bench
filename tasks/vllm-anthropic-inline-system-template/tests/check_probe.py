#!/usr/bin/env python3
"""Require every case, terminal stream event and exact token-count check."""
import json
from pathlib import Path
import sys

from probe_contract import MODE_SPECS, cases


def validate_mode(payload, mode):
    assert payload["mode"] == mode and payload["completed"] is True
    inventory = cases(mode)
    assert set(payload["cases"]) == set(inventory)
    reference = payload["reference_counts"]
    requires_reference = MODE_SPECS[mode]["family"] in {"permissive", "context"}
    assert set(reference) == (set(inventory) if requires_reference else set())
    operations = 0
    for name, case in inventory.items():
        result = payload["cases"][name]
        names = {"count_tokens", "messages"} | ({"stream"} if case.get("stream") else set())
        assert set(result) == names
        for operation in names:
            observed = result[operation]
            assert observed["ok"] is True, (name, operation, observed)
            assert type(observed["input_tokens"]) is int and observed["input_tokens"] > 0
        count = result["count_tokens"]["input_tokens"]
        assert result["messages"]["role"] == "assistant"
        assert count == result["messages"]["input_tokens"], (name, "count/generation mismatch", result)
        if case.get("stream"):
            stream = result["stream"]
            assert stream["role"] == "assistant" and stream["events"] >= 2
            assert stream["first_event"] == "message_start" and stream["last_event"] == "message_stop"
            assert count == stream["input_tokens"], (name, "count/stream mismatch", result)
        if requires_reference:
            assert type(reference[name]) is int and count == reference[name], (name, "independent tokenizer mismatch", count, reference[name])
        operations += len(names)
    return {"cases": len(inventory), "operations": operations}


def main():
    root = Path(sys.argv[1])
    results = {}
    errors = {}
    for mode in MODE_SPECS:
        try:
            payload = json.loads((root / f"{mode}_probe.json").read_text())
            results[mode] = validate_mode(payload, mode)
        except (OSError, ValueError, KeyError, TypeError, AssertionError, IndexError) as exc:
            errors[mode] = f"{type(exc).__name__}: {exc}"
    try:
        status = json.loads((root / "run-status.json").read_text())
        assert status["completed"] is True and set(status["exit_codes"]) == set(MODE_SPECS)
        assert all(type(code) is int and code == 0 for code in status["exit_codes"].values()), status
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        errors["completion"] = f"{type(exc).__name__}: {exc}"
    summary = {"passed": not errors, "modes": results, "errors": errors,
               "sdk_operations": sum(item["operations"] for item in results.values())}
    (root / "check-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
