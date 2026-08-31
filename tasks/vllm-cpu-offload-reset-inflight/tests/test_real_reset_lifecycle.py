#!/usr/bin/env python3
"""Run reset behavior across a real scheduler/worker process boundary."""

from __future__ import annotations

import multiprocessing as mp
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "/workspace/vllm")

from tests.v1.simple_kv_offload import test_harbor_reset_inflight as suite
from tests.v1.simple_kv_offload import test_scheduler as helpers
from vllm.v1.core.sched.scheduler import Scheduler
from vllm.v1.structured_output import StructuredOutputManager


def _worker(commands, completions):
    from vllm.v1.outputs import KVConnectorOutput
    from vllm.v1.simple_kv_offload.metadata import SimpleCPUOffloadWorkerMetadata

    while True:
        command = commands.get()
        if command is None:
            return
        kind, value = command
        time.sleep(0.2)
        if kind == "store":
            output = KVConnectorOutput(
                finished_recving=set(),
                kv_connector_worker_meta=SimpleCPUOffloadWorkerMetadata(
                    completed_store_events={value: 1}
                ),
            )
        else:
            output = KVConnectorOutput(
                finished_sending=set(),
                finished_recving={value},
            )
        completions.put(output)


class _Patch:
    @staticmethod
    def setattr(target, name, value):
        setattr(target, name, value)


def _roundtrip(commands, completions, connector, kind, value):
    commands.put((kind, value))
    output = completions.get(timeout=10)
    connector.update_connector_output(output)


def _make_scheduler(lazy: bool):
    original_model_config = helpers.ModelConfig
    try:
        with tempfile.TemporaryDirectory(prefix=f"reset-e2e-{lazy}-") as temp_dir:
            suite._use_offline_model_config(Path(temp_dir), _Patch())
            base = helpers.make_scheduler(
                num_cpu_blocks=12,
                num_gpu_blocks=20,
                lazy=lazy,
            )
    finally:
        helpers.ModelConfig = original_model_config

    bytes_per_block = sum(
        tensor.size for tensor in base.kv_cache_config.kv_cache_tensors
    ) // base.kv_cache_config.num_blocks
    base.vllm_config.kv_transfer_config.kv_connector_extra_config = {
        "cpu_bytes_to_use": bytes_per_block * 12,
        "lazy_offload": lazy,
    }
    base.vllm_config.cache_config.num_gpu_blocks = 20
    scheduler = Scheduler(
        vllm_config=base.vllm_config,
        kv_cache_config=base.kv_cache_config,
        block_size=helpers.BLOCK_SIZE,
        log_stats=True,
        structured_output_manager=StructuredOutputManager(base.vllm_config),
    )
    connector = scheduler.connector
    assert connector is not None
    assert connector.scheduler_manager is not None
    fix = suite.ConnectorFixture(
        connector=connector,
        scheduler_fixture=helpers.SchedulerFixture(
            scheduler=connector.scheduler_manager,
            gpu_block_pool=scheduler.kv_cache_manager.block_pool,
            vllm_config=base.vllm_config,
            kv_cache_config=base.kv_cache_config,
        ),
    )
    return scheduler, fix


def _run_mode(lazy: bool, commands, completions) -> None:
    scheduler, fix = _make_scheduler(lazy)
    source_blocks = 1 if lazy else 3
    source = helpers.make_request(
        num_blocks=source_blocks,
        request_id=f"e2e-old-{lazy}",
    )
    store_metadata = suite._start_store(
        fix,
        source,
        lazy=lazy,
        num_blocks=source_blocks,
    )
    commands.put(("store", store_metadata.store_event))
    assert scheduler.reset_prefix_cache(reset_connector=True) is False
    fix.connector.update_connector_output(completions.get(timeout=10))
    assert scheduler.reset_prefix_cache(reset_connector=True) is True
    assert suite._observed_hit(fix.connector, source, "old-store")[0] == 0

    fresh_blocks = 2
    fresh = helpers.make_request(
        num_blocks=fresh_blocks,
        request_id=f"e2e-fresh-{lazy}",
    )
    fresh_store = suite._start_store(
        fix,
        fresh,
        lazy=lazy,
        num_blocks=fresh_blocks,
    )
    _roundtrip(
        commands,
        completions,
        fix.connector,
        "store",
        fresh_store.store_event,
    )
    assert suite._observed_hit(fix.connector, fresh, "fresh-hit")[0] > 0

    loading, _load_metadata = suite._start_load(
        fix,
        fresh,
        f"e2e-loading-{lazy}",
    )
    commands.put(("load", loading.request_id))
    assert scheduler.reset_prefix_cache(reset_connector=True) is False
    fix.connector.update_connector_output(completions.get(timeout=10))
    assert scheduler.reset_prefix_cache(reset_connector=True) is True
    assert suite._observed_hit(fix.connector, fresh, "old-load")[0] == 0

    after_blocks = 3 if lazy else 1
    after = helpers.make_request(
        num_blocks=after_blocks,
        request_id=f"e2e-after-{lazy}",
    )
    after_store = suite._start_store(
        fix,
        after,
        lazy=lazy,
        num_blocks=after_blocks,
    )
    _roundtrip(
        commands,
        completions,
        fix.connector,
        "store",
        after_store.store_event,
    )
    assert suite._observed_hit(fix.connector, after, "after-hit")[0] > 0


def main() -> int:
    context = mp.get_context("spawn")
    commands = context.Queue()
    completions = context.Queue()
    worker = context.Process(target=_worker, args=(commands, completions), daemon=True)
    worker.start()
    try:
        _run_mode(False, commands, completions)
        _run_mode(True, commands, completions)
        print(
            {
                "modes": ["eager", "lazy"],
                "worker_process": worker.pid,
                "entrypoint": "Scheduler.reset_prefix_cache(reset_connector=True)",
                "store_reset_cycles": 4,
                "load_reset_cycles": 2,
                "old_cache_hits_after_reset": 0,
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        lines = str(exc).splitlines()
        print(
            {
                "error": type(exc).__name__,
                "message": lines[0] if lines else "no exception message",
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
