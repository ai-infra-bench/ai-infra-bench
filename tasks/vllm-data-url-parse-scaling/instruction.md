Large inline images noticeably delay multimodal request preprocessing before decoding starts. Profiling attributes about 70 ms for a 10 MB base64 data URL on the reported host to generic URL parsing alone, before media decoding begins.

Run the bundled public benchmark:

```bash
python /opt/repro/data_url_latency.py
```

Remove that avoidable full-URL parsing cost from `MediaConnector` data-URL dispatch. Synchronous and asynchronous data URLs must retain their media type and payload, including mixed-case schemes. Real image decoding, HTTP domain checks and downloads, file URLs, invalid schemes, malformed data URLs, and non-base64 rejection must keep working. The improvement must hold for large payloads without special-casing the benchmark size.
