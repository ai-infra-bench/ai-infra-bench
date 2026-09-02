from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import ray

from domain import load_requests
from gateway_config import GatewaySettings, parse_args
from pipeline import admission_settings_payload, plan_remote_batch, request_payloads
from runtime import VllmRuntime, engine_settings_payload


LOGGER = logging.getLogger("prompt_gateway")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


class PromptGatewayApplication:
    def __init__(self, settings: GatewaySettings, output: Path | None) -> None:
        self._settings = settings
        self._output = output
        self._runtime = None

    def _start_ray(self) -> None:
        ray_kwargs: dict[str, Any] = {
            "num_cpus": self._settings.ray.num_cpus,
            "include_dashboard": False,
            "log_to_driver": self._settings.ray.log_to_driver,
            "ignore_reinit_error": True,
        }
        if self._settings.ray.object_store_memory is not None:
            ray_kwargs["object_store_memory"] = self._settings.ray.object_store_memory
        ray.init(**ray_kwargs)
        LOGGER.debug("local Ray runtime started")

    def _start_runtime(self) -> None:
        self._runtime = VllmRuntime.remote(engine_settings_payload(self._settings.engine))
        health = ray.get(self._runtime.health.remote())
        if not health["ready"]:
            raise RuntimeError("vLLM runtime did not become ready")

    def _load_requests(self):
        requests = load_requests(self._settings.requests_path)
        LOGGER.info("loaded %d requests from %s", len(requests), self._settings.requests_path)
        return requests

    def _fetch_runtime_tokenizer(self):
        if self._runtime is None:
            raise RuntimeError("runtime actor has not been started")
        return ray.get(self._runtime.get_runtime_tokenizer.remote())

    def _plan(self, tokenizer, requests) -> dict[str, Any]:
        future = plan_remote_batch.remote(
            tokenizer,
            request_payloads(requests),
            admission_settings_payload(self._settings.admission),
        )
        return ray.get(future)

    def _write_report(self, report: dict[str, Any]) -> None:
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if self._output is None:
            print(rendered)
            return
        self._output.parent.mkdir(parents=True, exist_ok=True)
        self._output.write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("wrote batch plan to %s", self._output)

    def run(self) -> int:
        started = time.monotonic()
        self._start_ray()
        try:
            self._start_runtime()
            requests = self._load_requests()
            tokenizer = self._fetch_runtime_tokenizer()
            report = self._plan(tokenizer, requests)
            self._write_report(report)
            LOGGER.info("gateway completed in %.3f seconds", time.monotonic() - started)
            return 0
        except Exception:
            LOGGER.exception("prompt gateway failed while preparing the next request batch")
            return 1
        finally:
            ray.shutdown()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    settings = GatewaySettings.load(args.config)
    LOGGER.info("starting prompt gateway with config %s", args.config.resolve())
    return PromptGatewayApplication(settings, args.output).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
