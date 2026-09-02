from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineSettings:
    model_path: Path
    max_model_len: int
    max_num_seqs: int
    max_num_batched_tokens: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any], root: Path) -> "EngineSettings":
        model_path = Path(str(data.get("model_path", "model")))
        if not model_path.is_absolute():
            model_path = root / model_path
        settings = cls(
            model_path=model_path.resolve(),
            max_model_len=int(data.get("max_model_len", 128)),
            max_num_seqs=int(data.get("max_num_seqs", 8)),
            max_num_batched_tokens=int(data.get("max_num_batched_tokens", 256)),
        )
        if settings.max_model_len < 16:
            raise ValueError("max_model_len must be at least 16")
        if settings.max_num_seqs < 1:
            raise ValueError("max_num_seqs must be positive")
        if settings.max_num_batched_tokens < settings.max_model_len:
            raise ValueError("max_num_batched_tokens must cover one maximum-length request")
        return settings


@dataclass(frozen=True)
class AdmissionSettings:
    request_token_limit: int
    batch_token_limit: int
    max_batch_size: int
    reserve_output_tokens: int

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AdmissionSettings":
        settings = cls(
            request_token_limit=int(data.get("request_token_limit", 96)),
            batch_token_limit=int(data.get("batch_token_limit", 160)),
            max_batch_size=int(data.get("max_batch_size", 4)),
            reserve_output_tokens=int(data.get("reserve_output_tokens", 16)),
        )
        if settings.request_token_limit < 1:
            raise ValueError("request_token_limit must be positive")
        if settings.batch_token_limit < settings.request_token_limit:
            raise ValueError("batch_token_limit must cover one accepted request")
        if settings.max_batch_size < 1:
            raise ValueError("max_batch_size must be positive")
        if settings.reserve_output_tokens < 0:
            raise ValueError("reserve_output_tokens cannot be negative")
        return settings


@dataclass(frozen=True)
class RaySettings:
    num_cpus: int
    object_store_memory: int | None
    log_to_driver: bool

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "RaySettings":
        raw_store = data.get("object_store_memory")
        settings = cls(
            num_cpus=int(data.get("num_cpus", 4)),
            object_store_memory=None if raw_store is None else int(raw_store),
            log_to_driver=bool(data.get("log_to_driver", False)),
        )
        if settings.num_cpus < 2:
            raise ValueError("Ray needs at least two CPUs for this gateway")
        return settings


@dataclass(frozen=True)
class GatewaySettings:
    engine: EngineSettings
    admission: AdmissionSettings
    ray: RaySettings
    requests_path: Path

    @classmethod
    def load(cls, path: Path) -> "GatewaySettings":
        path = path.resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        root = path.parent
        requests_path = Path(str(data.get("requests_path", "requests.jsonl")))
        if not requests_path.is_absolute():
            requests_path = root / requests_path
        settings = cls(
            engine=EngineSettings.from_mapping(dict(data.get("engine", {})), root),
            admission=AdmissionSettings.from_mapping(dict(data.get("admission", {}))),
            ray=RaySettings.from_mapping(dict(data.get("ray", {}))),
            requests_path=requests_path.resolve(),
        )
        if not settings.engine.model_path.is_dir():
            raise FileNotFoundError(f"model directory not found: {settings.engine.model_path}")
        if not settings.requests_path.is_file():
            raise FileNotFoundError(f"request input not found: {settings.requests_path}")
        return settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="prompt-gateway",
        description="Plan token-budgeted request batches using a remote vLLM runtime.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("settings.json"),
        help="path to the gateway JSON configuration",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="optional path for the resulting batch plan",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser.parse_args(argv)
