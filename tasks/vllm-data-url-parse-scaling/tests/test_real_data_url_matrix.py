from __future__ import annotations

import asyncio
import json

from connector_fixture import ProbeMediaIO, data_url, load_async, median_ms
from vllm.multimodal.media.connector import MediaConnector


def main() -> int:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    payload_size = 6 * 1024 * 1024 + 17
    url = data_url(payload_size, scheme="DaTa", media_type="application/x-hidden")
    sync_ms, sync_result = median_ms(lambda: connector.load_from_url(url, media_io))
    async_ms, async_result = median_ms(
        lambda: asyncio.run(load_async(connector, url, media_io))
    )
    report = {
        "entrypoint": "real MediaConnector dispatch",
        "payload_size": payload_size,
        "sync_ms": round(sync_ms, 3),
        "async_ms": round(async_ms, 3),
        "sync_result": sync_result,
        "async_result": async_result,
        "bounded": sync_ms < 15.0 and async_ms < 20.0,
    }
    print(json.dumps(report, separators=(",", ":")))
    assert sync_result == async_result == ("application/x-hidden", payload_size)
    assert report["bounded"]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
