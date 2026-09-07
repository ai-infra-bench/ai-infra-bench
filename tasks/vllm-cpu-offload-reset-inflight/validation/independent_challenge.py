#!/usr/bin/env python3
"""Curator-only liveness challenge with an unseen four-block prefix."""

from pathlib import Path
import tempfile

from verifier_support import (
    complete_transfer,
    make_harness,
    make_request,
    observed_hit,
    populate_cache,
    reset,
    start_load,
    start_store,
)


def check_pending(harness):
    assert harness.connector.has_pending_push_work() is True
    assert harness.scheduler.has_requests() is True


def run_mode(root: Path, lazy: bool):
    harness = make_harness(
        root,
        lazy=lazy,
        num_cpu_blocks=20,
        num_gpu_blocks=28,
    )
    old_store = make_request(
        f"independent-store-{lazy}", num_blocks=4, token_seed=180000
    )
    store = start_store(harness, old_store, 4)
    assert reset(harness) is False
    check_pending(harness)
    complete_transfer(harness, store)
    assert reset(harness) is True
    assert observed_hit(harness, old_store, f"old-store-{lazy}")[0] == 0

    cached = make_request(
        f"independent-load-{lazy}", num_blocks=4, token_seed=190000
    )
    populate_cache(harness, cached, 4)
    _request, load, _metadata = start_load(
        harness, cached, f"independent-loading-{lazy}"
    )
    assert reset(harness) is False
    check_pending(harness)
    complete_transfer(harness, load)
    assert reset(harness) is True
    assert observed_hit(harness, cached, f"old-load-{lazy}")[0] == 0


def main():
    with tempfile.TemporaryDirectory(prefix="cpu-offload-independent-") as temp:
        root = Path(temp)
        run_mode(root / "eager", False)
        run_mode(root / "lazy", True)
    print(
        {
            "passed": True,
            "modes": ["eager", "lazy"],
            "prefix_blocks": 4,
            "store_liveness": True,
            "load_liveness": True,
            "old_hits_after_reset": 0,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
