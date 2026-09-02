from __future__ import annotations

import json

from unicode_fixture import run


def main() -> int:
    reasoning, content = run()
    result = {
        "entrypoint": "real split engine parser with two-token streaming deltas",
        "reasoning": reasoning,
        "content": content,
        "replacement_character_present": "�" in content,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if result["replacement_character_present"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
