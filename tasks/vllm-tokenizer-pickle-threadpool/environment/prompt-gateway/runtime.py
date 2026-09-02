from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

import ray

from gateway_config import EngineSettings


@ray.remote(num_cpus=2)
class VllmRuntime:
    def __init__(self, raw_settings: dict[str, Any]) -> None:
        os.environ.setdefault("VLLM_LOGGING_LEVEL", "WARNING")
        os.environ.setdefault("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
        os.environ.setdefault("VLLM_CPU_KVCACHE_SPACE", "1")
        from vllm import LLM

        settings = EngineSettings(
            model_path=raw_settings["model_path"],
            max_model_len=int(raw_settings["max_model_len"]),
            max_num_seqs=int(raw_settings["max_num_seqs"]),
            max_num_batched_tokens=int(raw_settings["max_num_batched_tokens"]),
        )
        self._settings = settings
        self._engine = LLM(
            model=str(settings.model_path),
            tokenizer=str(settings.model_path),
            load_format="dummy",
            dtype="float32",
            enforce_eager=True,
            trust_remote_code=False,
            max_model_len=settings.max_model_len,
            max_num_seqs=settings.max_num_seqs,
            max_num_batched_tokens=settings.max_num_batched_tokens,
            disable_log_stats=True,
        )

    def health(self) -> dict[str, Any]:
        tokenizer = self._engine.get_tokenizer()
        tokenizer.encode("health check", add_special_tokens=False)
        return {
            "ready": True,
            "max_model_len": self._settings.max_model_len,
        }

    def get_runtime_tokenizer(self):
        return self._engine.get_tokenizer()

    def settings(self) -> dict[str, Any]:
        result = asdict(self._settings)
        result["model_path"] = str(self._settings.model_path)
        return result


def engine_settings_payload(settings: EngineSettings) -> dict[str, Any]:
    return {
        "model_path": str(settings.model_path),
        "max_model_len": settings.max_model_len,
        "max_num_seqs": settings.max_num_seqs,
        "max_num_batched_tokens": settings.max_num_batched_tokens,
    }
