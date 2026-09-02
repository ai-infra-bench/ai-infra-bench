from __future__ import annotations

import json

from tokenizer_fixture import run


def main() -> int:
    result = run()
    result["entrypoint"] = "real HF fast tokenizer through pickle and spawn"
    print(json.dumps(result, indent=2))
    passed = (
        result["wrapped_thread_safe"]
        and not result["pickle_is_none"]
        and result["pickle_ids"] == [1, 2]
        and result["spawn_ids"] == [1, 2]
        and result["spawn_exit_code"] == 0
    )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
