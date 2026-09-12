Implement session-based streaming input for vLLM v1. Through the public asynchronous generation interface, a caller may provide an ordered stream of input chunks for one logical generation session, and a new chunk may arrive while the previous chunk is still being processed. The engine must accept chunks in order, continue the same session, and return generated output without duplicating or losing tokens.

Each continuation must preserve the session's valid context while applying the new input. The renewed prompt and per-segment request state must stay consistent across the request lifecycle, and previous output that is no longer part of the renewed prompt must not remain active. Multiple sessions may be interleaved without affecting one another.

Streaming must remain correct when inputs arrive in a burst or with delays, when the input stream closes after one or more chunks, and when a request ID is reused after the previous session has ended. Ordinary non-streaming request behavior must remain unchanged.

Keep the implementation within the existing vLLM v1 session and generation lifecycle; model-specific output quality and hardware-kernel performance are outside this task.
