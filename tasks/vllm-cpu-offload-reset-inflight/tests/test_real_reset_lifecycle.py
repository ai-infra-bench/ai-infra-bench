#!/usr/bin/env python3
"""Run reset behavior across a real Scheduler and a completion process."""

from __future__ import annotations

import multiprocessing as mp
import tempfile
import time
from pathlib import Path

from verifier_support import (
    assert_fresh_store_works,
    complete_transfer,
    make_harness,
    make_request,
    observed_hit,
    populate_cache,
    reset,
    start_load,
    start_store,
)


def _worker(commands, completions):
    while True:
        command = commands.get()
        if command is None:
            return
        time.sleep(command.get("delay", 0.05))
        completions.put(command["name"])


def _complete_via_process(commands, completions, harness, name, transfer):
    commands.put({"name": name, "delay": 0.05})
    assert completions.get(timeout=10) == name
    complete_transfer(harness, transfer)


def _run_mode(lazy, model_dir, commands, completions):
    harness = make_harness(model_dir, lazy=lazy)
    old_store = make_request(
        f"e2e-old-store-{lazy}", num_blocks=3, token_seed=130000
    )
    store_transfer = start_store(harness, old_store, 3)
    commands.put({"name": "store", "delay": 0.15})
    assert reset(harness) is False
    assert completions.get(timeout=10) == "store"
    complete_transfer(harness, store_transfer)
    assert reset(harness) is True
    assert observed_hit(harness, old_store, "e2e-old-store")[0] == 0

    fresh = make_request(
        f"e2e-fresh-{lazy}", num_blocks=2, token_seed=140000
    )
    fresh_store = start_store(harness, fresh, 2)
    _complete_via_process(
        commands, completions, harness, "fresh-store", fresh_store
    )
    assert observed_hit(harness, fresh, "e2e-fresh-hit")[0] > 0

    _loading, load_transfer, _metadata = start_load(
        harness, fresh, f"e2e-loading-{lazy}"
    )
    late_store = make_request(
        f"e2e-late-store-{lazy}", num_blocks=1, token_seed=150000
    )
    late_store_transfer = start_store(harness, late_store, 1)
    assert reset(harness) is False
    _complete_via_process(
        commands, completions, harness, "load", load_transfer
    )
    assert reset(harness) is False
    _complete_via_process(
        commands, completions, harness, "late-store", late_store_transfer
    )
    assert reset(harness) is True
    assert observed_hit(harness, fresh, "e2e-old-load")[0] == 0
    assert observed_hit(harness, late_store, "e2e-late-store")[0] == 0
    assert_fresh_store_works(harness, 160000 if lazy else 170000)


def main():
    context = mp.get_context("spawn")
    commands = context.Queue()
    completions = context.Queue()
    worker = context.Process(target=_worker, args=(commands, completions), daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="offload-reset-e2e-") as temp_dir:
            root = Path(temp_dir)
            _run_mode(False, root / "eager", commands, completions)
            _run_mode(True, root / "lazy", commands, completions)
        print(
            {
                "modes": ["eager", "lazy"],
                "worker_process": worker.pid,
                "entrypoint": "Scheduler.reset_prefix_cache(reset_connector=True)",
                "store_and_load_overlap": True,
                "old_cache_hits_after_reset": 0,
                "post_reset_store_and_hit": True,
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            {
                "error": type(exc).__name__,
                "message": str(exc).splitlines()[0] if str(exc) else "no message",
            },
            flush=True,
        )
        return 1
    finally:
        commands.put(None)
        worker.join(timeout=10)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
