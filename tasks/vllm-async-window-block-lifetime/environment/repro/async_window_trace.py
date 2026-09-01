from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scheduler_fixture import (
    async_free_timeline,
    competing_load_reuse,
    speculative_rollback_window,
    sync_free_timeline,
)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="async-window-trace-"))
    async_swa = async_free_timeline(root / "async-swa", "swa")
    async_chunked = async_free_timeline(root / "async-chunked", "chunked")
    sync_swa = sync_free_timeline(root / "sync-swa", "swa")
    load_reuse = competing_load_reuse(root / "load-reuse", "swa")
    rollback = speculative_rollback_window(
        root / "rollback",
        "swa",
        rollback_tokens=32,
    )
    print(
        json.dumps(
            {
                "async_swa": async_swa,
                "async_chunked": async_chunked,
                "sync_swa": sync_swa,
                "load_reuse": load_reuse,
                "speculative_rollback": rollback,
            },
            indent=2,
        )
    )
    correct = (
        async_swa["before_process"] == async_swa["after_prefill"]
        and async_chunked["before_process"] == async_chunked["after_prefill"]
        and sync_swa["after_decode"] > sync_swa["before_decode"]
        and not load_reuse["premature_overlap"]
        and rollback["required_blocks_retained"]
    )
    print(f"inflight_window_lifetime_contract={correct}")
    return 0 if correct else 3


if __name__ == "__main__":
    raise SystemExit(main())
