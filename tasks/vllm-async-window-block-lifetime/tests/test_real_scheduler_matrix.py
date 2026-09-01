from __future__ import annotations

import json
import tempfile
from pathlib import Path

from verifier_support import (
    admission_blocks,
    async_free_timeline,
    competing_load_reuse,
    connector_handoff_distinct_block_count,
    pipeline_free_timeline,
    speculative_rollback_window,
    sync_free_timeline,
)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="async-window-e2e-"))
    async_swa = async_free_timeline(root / "async-swa", "swa")
    async_chunked = async_free_timeline(root / "async-chunked", "chunked")
    sync_swa = sync_free_timeline(root / "sync-swa", "swa")
    pipeline_swa = pipeline_free_timeline(root / "pipeline-swa", "swa")
    connector_blocks = connector_handoff_distinct_block_count(root / "connector")
    load_reuse = competing_load_reuse(root / "load-reuse", "chunked")
    rollback = speculative_rollback_window(
        root / "rollback",
        "swa",
        rollback_tokens=53,
    )
    assert async_swa["before_process"] == async_swa["after_prefill"]
    assert async_swa["after_process"] - async_swa["after_prefill"] == 5
    assert async_chunked["before_process"] == async_chunked["after_prefill"]
    assert async_chunked["after_process"] - async_chunked["after_prefill"] == 6
    assert sync_swa["after_decode"] - sync_swa["before_decode"] == 5
    assert pipeline_swa["before_process"] == pipeline_swa["after_prefill"]
    assert pipeline_swa["after_process"] - pipeline_swa["after_prefill"] == 5
    assert connector_blocks == 7
    assert load_reuse["premature_overlap"] == []
    assert rollback["required_blocks_retained"]
    assert admission_blocks(root / "admission-a", "swa", async_scheduling=True) > (
        admission_blocks(root / "admission-s", "swa", async_scheduling=False)
    )
    print(
        json.dumps(
            {
                "entrypoint": "real Scheduler schedule/update/finish lifecycle",
                "async_swa": async_swa,
                "async_chunked": async_chunked,
                "sync_swa": sync_swa,
                "pipeline_swa": pipeline_swa,
                "connector_handoff_blocks": connector_blocks,
                "competing_load_reuse": load_reuse,
                "speculative_rollback": rollback,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
