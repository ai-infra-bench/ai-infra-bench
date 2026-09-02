from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from connector_fixture import (
    FakeConnection,
    ProbeMediaIO,
    data_url,
    image_data_url,
    load_async,
    median_ms,
)
from vllm.multimodal.media.connector import MediaConnector


def test_large_sync_data_url_avoids_generic_parser_overhead() -> None:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    large_ms, result = median_ms(
        lambda: connector.load_from_url(data_url(8 * 1024 * 1024), media_io)
    )
    assert result == ("application/x-probe", 8 * 1024 * 1024)
    assert large_ms < 15.0


def test_large_async_data_url_avoids_generic_parser_overhead() -> None:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    url = data_url(8 * 1024 * 1024)
    elapsed, result = median_ms(
        lambda: asyncio.run(load_async(connector, url, media_io))
    )
    assert result == ("application/x-probe", 8 * 1024 * 1024)
    assert elapsed < 20.0


def test_mixed_case_data_scheme_preserves_type_and_payload() -> None:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    url = data_url(37, scheme="DaTa", media_type="image/x-case")
    assert connector.load_from_url(url, media_io) == ("image/x-case", 37)
    assert asyncio.run(load_async(connector, url, media_io)) == ("image/x-case", 37)


def test_real_png_decodes_through_sync_and_async_paths() -> None:
    connector = MediaConnector()
    sync_image = connector.fetch_image(image_data_url())
    async_image = asyncio.run(connector.fetch_image_async(image_data_url(scheme="DATA")))
    assert sync_image.size == async_image.size == (3, 2)
    assert sync_image.getpixel((0, 0)) == async_image.getpixel((0, 0)) == (12, 34, 56)


def test_http_domain_checks_and_downloads_remain_active() -> None:
    connection = FakeConnection()
    connector = MediaConnector(connection=connection, allowed_media_domains=["allowed.test"])
    media_io = ProbeMediaIO()
    assert connector.load_from_url("https://allowed.test/a.bin", media_io) == ("bytes", 10)
    assert asyncio.run(
        load_async(connector, "https://allowed.test/b.bin", media_io)
    ) == ("bytes", 10)
    assert connection.sync_urls == ["https://allowed.test/a.bin"]
    assert connection.async_urls == ["https://allowed.test/b.bin"]
    with pytest.raises(ValueError, match="allowed domains"):
        connector.load_from_url("https://blocked.test/a.bin", media_io)


def test_file_urls_keep_allowlist_and_traversal_checks(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    item = allowed / "item.bin"
    item.write_bytes(b"abc")
    connector = MediaConnector(allowed_local_media_path=str(allowed))
    media_io = ProbeMediaIO()
    assert connector.load_from_url(item.as_uri(), media_io) == ("file", 3)
    assert asyncio.run(load_async(connector, item.as_uri(), media_io)) == ("file", 3)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="must be a subpath"):
        connector.load_from_url(outside.as_uri(), media_io)


def test_unsupported_scheme_still_fails() -> None:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    with pytest.raises(ValueError, match="HTTP, data or file"):
        connector.load_from_url("ftp://example.test/a", media_io)
    with pytest.raises(ValueError, match="HTTP, data or file"):
        asyncio.run(load_async(connector, "blob:anything", media_io))


@pytest.mark.parametrize("url", ["data:image/png;base64", "data:image/png"])
def test_malformed_data_urls_still_fail(url: str) -> None:
    with pytest.raises(ValueError):
        MediaConnector().load_from_url(url, ProbeMediaIO())


def test_non_base64_data_url_still_fails() -> None:
    connector, media_io = MediaConnector(), ProbeMediaIO()
    with pytest.raises(NotImplementedError, match="Only base64"):
        connector.load_from_url("data:text/plain;charset=utf-8,hello", media_io)
    with pytest.raises(NotImplementedError, match="Only base64"):
        asyncio.run(
            load_async(connector, "DATA:text/plain;charset=utf-8,hello", media_io)
        )
