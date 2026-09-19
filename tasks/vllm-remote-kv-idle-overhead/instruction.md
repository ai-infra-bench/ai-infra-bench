I use vLLM for disaggregated serving with asynchronous remote KV transfer. When a large batch is waiting for remote KV data, the scheduler burns CPU even though the transfers have made no progress. Adding more unchanged waiting requests makes each idle tick slower. A small version of the workload looks like this:

```text
Arrival order: A, B, C
A and B need remote KV data; their transfers are still pending.
C can run without waiting for a remote transfer.
B's transfer completes first, then A's.
```

I need C to keep making progress while the transfers are pending, and A and B to resume when their data arrives. Please remove the idle overhead so a tick with no new remote event does not do work proportional to the blocked population. Keep the existing FCFS behavior among requests that can run, including when other requests are temporarily blocked for different reasons.

Request counts, cancellation during a transfer, normal generation and completion, and admission of subsequent requests should all keep working.

I also keep these workers alive for long runs, so finished requests must not leave steadily growing scheduler memory behind. For a one-request-at-a-time stream of short prompts (up to 64 tokens), I can allow 32 MiB of additional retained Python memory after warm-up. Bounded caches and delayed or batched cleanup are fine; I do not need every object freed immediately.
