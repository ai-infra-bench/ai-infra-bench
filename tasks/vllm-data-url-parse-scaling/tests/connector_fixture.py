from __future__ import annotations

import asyncio
import io
import statistics
import time
from pathlib import Path

from PIL import Image

from vllm.multimodal.media.base import MediaIO
from vllm.multimodal.media.connector import MediaConnector


class ProbeMediaIO(MediaIO[tuple[str, int]]):
    def load_bytes(self, data: bytes) -> tuple[str, int]:
        return "bytes", len(data)

    def load_base64(self, media_type: str, data: str) -> tuple[str, int]:
        return media_type, len(data)

    def load_file(self, filepath: Path) -> tuple[str, int]:
        return "file", filepath.stat().st_size


class FakeConnection:
    def __init__(self, data: bytes = b"downloaded") -> None:
        self.data = data
        self.sync_urls: list[str] = []
        self.async_urls: list[str] = []

    def get_bytes(self, url: str, **_: object) -> bytes:
        self.sync_urls.append(url)
        return self.data

    async def async_get_bytes(self, url: str, **_: object) -> bytes:
        self.async_urls.append(url)
        return self.data


def data_url(size: int, *, scheme: str = "data", media_type: str = "application/x-probe") -> str:
    return f"{scheme}:{media_type};base64," + "A" * size


def image_data_url(*, scheme: str = "data") -> str:
    image = Image.new("RGB", (3, 2), (12, 34, 56))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    import base64

    payload = base64.b64encode(buffer.getvalue()).decode()
    return f"{scheme}:image/png;base64,{payload}"


def median_ms(call, repeats: int = 5):
    elapsed = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter()
        result = call()
        elapsed.append((time.perf_counter() - started) * 1000)
    return statistics.median(elapsed), result


async def load_async(connector: MediaConnector, url: str, media_io: MediaIO):
    return await connector.load_from_url_async(url, media_io)
