We benchmark cold-cache time to first token and request throughput across different serving configurations. The suite reuses the same prompt set, so before each run it clears both the local and connector-managed prefix caches to prevent later runs from benefiting from KV data produced by earlier ones.

With `SimpleCPUOffloadConnector` enabled, calling `llm.reset_prefix_cache(reset_connector=True)` fails with:

```text
NotImplementedError: SimpleCPUOffloadConnector does not support reset_cache().
```

Implement this missing reset feature for both eager and lazy CPU-offload configurations. We may request a reset as soon as a benchmark run finishes, while data from the final requests is still being stored to CPU or loaded back for reuse.

If outstanding work prevents an immediate reset, the call should return `False`; retrying after that work settles should return `True`. After a successful reset, the next benchmark run must not hit entries from the previous one, delayed completions must not make old entries visible again, and subsequent requests must continue to run normally.
