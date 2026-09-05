#!/usr/bin/env python3
"""Unprivileged observation worker for the trusted verifier supervisor.

The worker imports candidate-controlled vLLM and executes exactly one case.
It never decides the reward and never reports aggregate success.  The trusted
parent owns the case list and interprets these raw observations.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

# ``-I`` prevents candidate-controlled environment variables from selecting a
# different package, so bind the one intended candidate repository explicitly.
sys.path.insert(0, "/workspace/repo")

import torch

import vllm.envs as envs
from vllm.config import CacheConfig, ModelConfig, VllmConfig


FIXTURES = {
    "qwen3": Path("/tests/fixtures/qwen3"),
    "qwen2": Path("/tests/fixtures/qwen2"),
}
RESULT_PREFIX = "AI_INFRA_OBSERVATION="


def set_override(value: str | None) -> None:
    if value is None:
        os.environ.pop("VLLM_USE_V2_MODEL_RUNNER", None)
    else:
        os.environ["VLLM_USE_V2_MODEL_RUNNER"] = value


def make_config(
    *,
    model: str = "qwen3",
    runner: str = "auto",
    quantization: str | None = None,
    kv_sharing: bool = False,
    logits_processors: list[str] | None = None,
    enable_prompt_embeds: bool = False,
) -> VllmConfig:
    model_config = ModelConfig(
        model=str(FIXTURES[model]),
        runner=runner,
        quantization=quantization,
        logits_processors=logits_processors,
        enable_prompt_embeds=enable_prompt_embeds,
        skip_tokenizer_init=True,
        dtype="float16",
    )
    return VllmConfig(
        model_config=model_config,
        cache_config=CacheConfig(kv_sharing_fast_prefill=kv_sharing),
    )


def construct_worker(config: VllmConfig) -> object:
    import vllm.distributed.elastic_ep.elastic_execute as elastic_execute
    from vllm.v1.worker.gpu_worker import Worker

    # Elastic EP is orthogonal control-plane state. Keep the production Worker
    # constructor and runner-selection consumer, while avoiding a distributed
    # process group for this focused configuration test.
    with patch.object(
        elastic_execute,
        "ElasticEPScalingExecutor",
        side_effect=lambda _worker: object(),
    ):
        return Worker(
            vllm_config=config,
            local_rank=0,
            rank=0,
            distributed_init_method="tcp://127.0.0.1:1",
            is_driver_worker=True,
        )


def selected(*, override: str | None, **kwargs: object) -> bool:
    set_override(override)
    return bool(construct_worker(make_config(**kwargs)).use_v2_model_runner)


SELECTION_CASES: dict[str, tuple[str | None, dict[str, object]]] = {
    "auto_dense_qwen3_worker_v2": (None, {}),
    "auto_other_arch_worker_v1": (None, {"model": "qwen2"}),
    "auto_pooling_worker_v1": (None, {"runner": "pooling"}),
    "auto_kv_sharing_worker_v1": (None, {"kv_sharing": True}),
    "auto_logits_processor_worker_v1": (
        None,
        {"logits_processors": ["example.Plugin"]},
    ),
    "forced_v1_supported_worker_v1": ("0", {}),
    "forced_v1_unsupported_worker_v1": ("0", {"kv_sharing": True}),
    "forced_v2_supported_worker_v2": ("1", {}),
    "forced_v2_other_arch_worker_v2": ("1", {"model": "qwen2"}),
}


REJECTION_CASES: dict[str, dict[str, object]] = {
    "forced_v2_kv_sharing_rejected": {"kv_sharing": True},
    "forced_v2_logits_processor_rejected": {
        "logits_processors": ["example.Plugin"]
    },
}


def observe(case: str) -> object:
    if case == "cuda_available":
        return torch.cuda.is_available()
    if case == "qwen3_fixture_available":
        return (FIXTURES["qwen3"] / "config.json").is_file()
    if case == "qwen2_fixture_available":
        return (FIXTURES["qwen2"] / "config.json").is_file()
    if case == "unset_accessor_readable":
        set_override(None)
        value = envs.VLLM_USE_V2_MODEL_RUNNER
        return {"type": type(value).__name__, "value": value}
    if case in {"explicit_zero_accessor", "explicit_one_accessor"}:
        set_override("0" if case == "explicit_zero_accessor" else "1")
        return envs.VLLM_USE_V2_MODEL_RUNNER
    if case in SELECTION_CASES:
        override, kwargs = SELECTION_CASES[case]
        return selected(override=override, **kwargs)
    if case in REJECTION_CASES:
        set_override("1")
        try:
            construct_worker(make_config(**REJECTION_CASES[case]))
        except Exception as exc:
            return {"rejected": True, "type": type(exc).__name__, "message": str(exc)}
        return {"rejected": False, "type": None, "message": ""}
    raise ValueError(f"unknown verifier case: {case}")


def main() -> int:
    request = json.loads(sys.stdin.readline())
    case = request["case"]
    nonce = request["nonce"]
    try:
        value = observe(case)
        result = {"case": case, "nonce": nonce, "value": value, "error": None}
    except Exception as exc:
        result = {
            "case": case,
            "nonce": nonce,
            "value": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    finally:
        set_override(None)
    print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
