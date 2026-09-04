#!/usr/bin/env python3
"""Run a reduced async KV lifecycle across a scheduler/worker process boundary."""

from __future__ import annotations

import multiprocessing as mp
import queue
import tempfile
import time
from pathlib import Path

from vllm.distributed.kv_transfer.kv_connector.factory import KVConnectorFactory
from vllm.distributed.kv_transfer.kv_connector.v1.base import KVConnectorRole
from vllm.v1.outputs import KVConnectorOutput

from verifier_support import (
    empty_output,
    make_cache_config,
    make_config,
    make_request,
    make_scheduler,
    sampled_output,
    tiny_model,
    tokens,
)


def _worker(model_dir, block_size, matches, delays, metadata, results):
    config = make_config(
        Path(model_dir),
        block_size=block_size,
        matches=matches,
        delays_ms=delays,
    )
    cache_config = make_cache_config(block_size)
    connector = KVConnectorFactory.create_connector(
        config,
        KVConnectorRole.WORKER,
        cache_config,
    )
    connector.bind_connector_metadata(metadata)
    connector.start_load_kv(None)
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            _, finished = connector.get_finished(set())
            invalid = connector.get_block_ids_with_load_errors()
            if finished or invalid:
                results.put((finished or set(), invalid))
            if len(connector.completed_checksums) == len(matches):
                results.put(("summary", connector.completed_checksums))
                return
            time.sleep(0.003)
        results.put(("error", "worker timeout"))
    finally:
        connector.shutdown()


def main() -> int:
    cases = [
        ("e2e-a", 58, 7),
        ("e2e-b", 81, 34),
        ("e2e-c", 113, 65),
    ]
    matches = {request_id: matched for request_id, _, matched in cases}
    delays = {"e2e-a": 5, "e2e-b": 45, "e2e-c": 90}
    context = mp.get_context("spawn")
    results = context.Queue()
    try:
        with tempfile.TemporaryDirectory(prefix="async-kv-e2e-") as temp_dir:
            model_dir = tiny_model(Path(temp_dir) / "model")
            scheduler, _config, _cache = make_scheduler(
                model_dir,
                block_size=16,
                matches=matches,
                delays_ms=delays,
            )
            for index, (request_id, prompt_tokens, _matched) in enumerate(cases):
                scheduler.add_request(
                    make_request(
                        request_id,
                        tokens(prompt_tokens, salt=701 + index * 43),
                        block_size=16,
                    )
                )
            initial = scheduler.schedule()
            assert not initial.num_scheduled_tokens
            process = context.Process(
                target=_worker,
                args=(
                    str(model_dir),
                    16,
                    matches,
                    delays,
                    initial.kv_connector_metadata,
                    results,
                ),
                daemon=True,
            )
            process.start()
            scheduler.update_from_output(initial, empty_output())
            observed = {}
            worker_summary = None
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and (
                len(observed) < len(cases) or worker_summary is None
            ):
                try:
                    kind, payload = results.get(timeout=1)
                except queue.Empty:
                    continue
                if kind == "summary":
                    worker_summary = payload
                    continue
                if kind == "error":
                    raise RuntimeError(payload)
                finished = kind
                waiting = scheduler.schedule()
                scheduler.update_from_output(
                    waiting,
                    empty_output(
                        KVConnectorOutput(
                            finished_recving=finished,
                            invalid_block_ids=payload,
                        )
                    ),
                )
                ready = scheduler.schedule()
                for item in ready.scheduled_new_reqs:
                    observed[item.req_id] = (
                        item.num_computed_tokens,
                        ready.num_scheduled_tokens[item.req_id],
                    )
                if ready.num_scheduled_tokens:
                    scheduler.update_from_output(ready, sampled_output(ready))
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
            assert process.exitcode == 0
            assert observed == {
                request_id: (matched, prompt - matched)
                for request_id, prompt, matched in cases
            }
            assert worker_summary is not None
            assert set(worker_summary) == set(matches)
            print(
                {
                    "entrypoint": "Scheduler + verifier connector process boundary",
                    "worker_process": process.pid,
                    "completed_requests": sorted(observed),
                    "copied_payload_checksums": len(worker_summary),
                    "runner_accounting": observed,
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


if __name__ == "__main__":
    raise SystemExit(main())
