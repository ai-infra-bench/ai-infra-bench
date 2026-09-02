Since upgrading vLLM, `LLM.get_tokenizer()` and `AsyncLLM.get_tokenizer()` still work in the engine process, but retrieving the tokenizer from a Ray actor or sending it through multiprocessing silently produces `None` on the receiving side. There is no serialization exception. The tokenizer returned by older vLLM releases survives the same transfer.

The image includes a local fast tokenizer and a process-boundary reproduction:

```bash
python /opt/repro/tokenizer_pickle_trace.py
```

Fix the thread-safe tokenizer wrapper so standard pickle, cloudpickle-style reconstruction, and spawned-process transfer return a usable tokenizer rather than `None`. Encoding, decoding, batched calls, configured pool sizes, repeated wrapping, and ordinary slow or already-wrapped tokenizers must keep their current behavior. Preserve thread-safe access; do not work around the problem by returning an unrelated raw tokenizer to callers that requested the pooled wrapper.
