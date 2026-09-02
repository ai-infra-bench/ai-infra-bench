from __future__ import annotations

import json

from tokenizer_fixture import is_thread_safe, pickle_roundtrip, pooled, spawn_roundtrip


def main() -> int:
    tokenizer = pooled(copies=2)
    restored = pickle_roundtrip(tokenizer)
    spawned = spawn_roundtrip(tokenizer)
    result = {
        "entrypoint": "HF fast tokenizer wrapper through pickle and multiprocessing spawn",
        "pickle_is_none": restored is None,
        "pickle_thread_safe": False if restored is None else is_thread_safe(restored),
        "pickle_ids": None if restored is None else restored.encode("hello world"),
        "spawn": spawned,
    }
    print(json.dumps(result, separators=(",", ":")))
    assert result["pickle_is_none"] is False
    assert result["pickle_thread_safe"] is True
    assert result["pickle_ids"] == [2, 3]
    assert spawned == {"is_none": False, "ids": [2, 3]}
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
