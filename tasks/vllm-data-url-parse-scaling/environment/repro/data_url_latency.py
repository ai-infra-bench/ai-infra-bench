from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path

from vllm.multimodal.media.base import MediaIO
from vllm.multimodal.media.connector import MediaConnector


class ProbeMediaIO(MediaIO[tuple[str, int]]):
    def load_bytes(self, data: bytes) -> tuple[str, int]:
        return "bytes", len(data)

    def load_base64(self, media_type: str, data: str) -> tuple[str, int]:
        return media_type, len(data)

    def load_file(self, filepath: Path) -> tuple[str, int]:
        return "file", filepath.stat().st_size


def _median_ms(call, repeats: int = 5) -> tuple[float, tuple[str, int]]:
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        samples.append((time.perf_counter() - started) * 1000)
    assert result is not None
    return statistics.median(samples), result


async def _async_once(connector: MediaConnector, url: str, media_io: ProbeMediaIO):
    return await connector.load_from_url_async(url, media_io)


def main() -> int:
    payload_size = 8 * 1024 * 1024
    url = "data:application/octet-stream;base64," + "A" * payload_size
    connector = MediaConnector()
    media_io = ProbeMediaIO()
    sync_ms, sync_result = _median_ms(
        lambda: connector.load_from_url(url, media_io)
    )
    async_ms, async_result = _median_ms(
        lambda: asyncio.run(_async_once(connector, url, media_io))
    )
    result = {
        "entrypoint": "MediaConnector sync and async URL dispatch",
        "payload_bytes": payload_size,
        "sync_median_ms": round(sync_ms, 3),
        "async_median_ms": round(async_ms, 3),
        "sync_result": sync_result,
        "async_result": async_result,
        "payload_preserved": sync_result == async_result == (
            "application/octet-stream",
            payload_size,
        ),
        "bounded_dispatch": sync_ms < 15.0 and async_ms < 20.0,
    }
    print(json.dumps(result, indent=2))
    return 0 if result["payload_preserved"] and result["bounded_dispatch"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
