We run two vLLM replicas for a MiniMax model with MTP/EAGLE-3 enabled and share prefixes through MooncakeStoreConnector. A prompt warmed on the first replica returns HTTP 200 when sent to the second replica, but the generated text can hallucinate a system prompt or drop and swap user turns. The same prompt is correct on a cold run and when MTP is disabled.

Tracing one 64-token stored prefix with a 16-token block size shows that lookup reports a 48-token external hit. The receiving replica enumerates chunks beginning at token offsets 0, 16, and 32, but only the first two are submitted to the store load operation; no transfer error is reported.

Investigate and fix the cross-instance cache-load corruption. Every chunk covered by the reported external hit must be populated on the receiving replica, while lookup behavior and non-MTP and hybrid-attention cache semantics must remain correct.
