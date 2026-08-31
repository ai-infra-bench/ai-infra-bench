#!/usr/bin/env python3
import json
import sys

EXPECTED = {
    "official_qwen": {
        "production_issue_shape", "inline_after_user_without_leading_system",
        "multiple_inline_system_messages", "top_level_and_inline_system",
        "system_text_blocks", "empty_inline_system", "long_context_inline_system",
    },
    "restrictive_sentinel": {"all_system_content_preserved"},
    "permissive": {"inline_position_preserved"},
}
STREAM_CASES = {
    "official_qwen": {"production_issue_shape", "multiple_inline_system_messages"},
    "restrictive_sentinel": {"all_system_content_preserved"},
    "permissive": {"inline_position_preserved"},
}

def main() -> int:
    valid = True
    summaries = {}
    for path in sys.argv[1:]:
        payload = json.load(open(path))
        mode = payload["mode"]
        cases = payload["cases"]
        valid &= set(cases) == EXPECTED[mode]
        for name, result in cases.items():
            valid &= result["count_tokens"]["ok"] is True
            valid &= result["count_tokens"]["input_tokens"] > 0
            valid &= result["messages"]["ok"] is True
            valid &= result["messages"]["role"] == "assistant"
            if name in STREAM_CASES[mode]:
                valid &= result["stream"]["ok"] is True
                valid &= result["stream"]["events"] > 0
        summaries[mode] = {"cases": len(cases), "all_ok": valid}
    print(summaries)
    return 0 if valid and set(summaries) == set(EXPECTED) else 1

if __name__ == "__main__":
    raise SystemExit(main())
