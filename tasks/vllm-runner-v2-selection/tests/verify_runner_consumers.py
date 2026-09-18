#!/usr/bin/env python3
"""Execute complete startup selection, with no candidate imports at module load."""
from __future__ import annotations

import gc
import os
import socket
import sys
import time
from pathlib import Path
from unittest.mock import patch


def run_suite(cases, emit):
    # The supervisor loads this code before forking and before candidate imports.
    # The emitter authenticates calls from this exact suite code object.
    sys.path.insert(0, "/workspace/repo")
    import torch
    from vllm.config import (
        CacheConfig, ModelConfig, SchedulerConfig, VllmConfig,
        set_current_vllm_config,
    )
    from vllm.distributed import cleanup_dist_env_and_memory
    from vllm.v1.worker.gpu_worker import Worker
    from vllm.v1.worker.gpu.model_runner import GPUModelRunner as RunnerV2
    from vllm.v1.worker.gpu_model_runner import GPUModelRunner as RunnerV1
    import vllm.distributed.elastic_ep.elastic_execute as elastic

    for case in cases:
        start = time.monotonic()
        worker = config = None
        result = {"runner": None, "error": None}
        if case["override"] is None:
            os.environ.pop("VLLM_USE_V2_MODEL_RUNNER", None)
        else:
            os.environ["VLLM_USE_V2_MODEL_RUNNER"] = case["override"]
        try:
            model = ModelConfig(
                model=str(Path("/tests/fixtures") / case.get("model", "qwen3")),
                skip_tokenizer_init=True,
                dtype="float16",
                enforce_eager=True,
                **case.get("model_options", {}),
            )
            config = VllmConfig(
                model_config=model,
                cache_config=CacheConfig(
                    gpu_memory_utilization=0.05,
                    kv_sharing_fast_prefill=case.get("kv_sharing", False),
                ),
                scheduler_config=SchedulerConfig(
                    max_num_seqs=4, max_num_batched_tokens=64,
                    max_model_len=model.max_model_len,
                    runner_type=model.runner_type,
                    is_encoder_decoder=model.is_encoder_decoder,
                ),
            )
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            # Elastic EP does not determine selection. Config, Worker startup,
            # distributed initialization and both runner constructors stay real.
            with set_current_vllm_config(config), patch.object(
                elastic, "ElasticEPScalingExecutor", side_effect=lambda _: object(),
            ):
                worker = Worker(config, 0, 0, f"tcp://127.0.0.1:{port}", True)
                worker.init_device()
            actual = worker.model_runner
            if isinstance(actual, RunnerV2):
                result["runner"] = "V2"
            elif isinstance(actual, RunnerV1):
                result["runner"] = "V1"
            else:
                result["runner"] = "unknown"
        except Exception as exc:
            result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            worker = config = None
            if "actual" in locals():
                del actual
            gc.collect()
            cleanup_dist_env_and_memory()
        result["seconds"] = round(time.monotonic() - start, 3)
        emit(case["name"], result)
