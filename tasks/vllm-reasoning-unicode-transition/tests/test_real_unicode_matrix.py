from __future__ import annotations

import json

from unicode_fixture import GlmDelegatingParser, QwenDelegatingParser, korean_tokens, parse


def main() -> int:
    cases = []
    for name, parser in (("glm", GlmDelegatingParser), ("qwen", QwenDelegatingParser)):
        for chunk_size in (1, 2, 3, None):
            result = parse(parser, korean_tokens(), {200}, chunk_size)
            cases.append(
                {
                    "parser": name,
                    "chunk_size": chunk_size,
                    "reasoning": result.reasoning,
                    "content": result.content,
                    "valid": result.content == "삼성전자의 주가입니다." and "�" not in result.content,
                }
            )
    print(json.dumps({"entrypoint": "real DelegatingParser engine matrix", "cases": cases}, ensure_ascii=False, separators=(",", ":")))
    assert all(case["valid"] for case in cases), cases
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
