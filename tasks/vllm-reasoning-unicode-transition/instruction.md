Our streamed chat responses occasionally contain a Unicode replacement character in otherwise valid Korean text, for example `...영�구에 있는...`. The failure appeared after enabling the engine parser with separate reasoning and tool parsers. It is most likely when a multi-byte character lands around the reasoning-to-content transition; identical requests may work with other token batching boundaries.

The full incident used a GLM server and the reporter observed it in roughly 20–40% of repeated requests. This image provides a deterministic CPU replay of the same parser boundary:

```bash
python /opt/repro/unicode_transition_trace.py
```

Fix streamed parser output so complete Unicode text is preserved across reasoning-to-content transitions for the supported engine-based GLM and Qwen parser combinations. Reasoning text, content, transition markers, tool parsing, ASCII output, multiple consecutive byte-fallback tokens, finish handling, and chunk-size invariance must remain correct. Do not hide corruption by deleting replacement characters after parsing.
