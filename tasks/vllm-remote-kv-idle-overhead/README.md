# vLLM remote-KV idle scheduling

Keep idle scheduler ticks independent of unchanged remote-KV waiters while preserving runnable FCFS, request accounting, cancellation, generation, completion and later admission. Long-running sequential short requests have the explicit retained Python memory budget in [instruction.md](instruction.md).

## Environment

The environment inputs are unchanged: the exact Base source, digest-pinned CPU runtime, offline public OPT/LLaVA config and tokenizer metadata, and a 36,000-second agent budget. Model arithmetic and remote-event production are substitutable inputs to this CPU scheduler task. The production scheduler, request queues, KV ownership transitions and EngineCore lifecycle remain real. See [environment provenance](environment/lock/README.md).

## Verification

Version 1.6.0 moves all behavioral assertions and final scoring into a root-owned parent that never imports candidate vLLM. Its interpreter starts with `-I -S`; site packages and candidate `.pth` files are loaded only after the worker drops to the agent UID. The worker exposes request operations and actual engine outputs, not pass/fail checkpoints. The parent checks request identities, counts, tokens, terminal events and admission decisions. Premature success exits cannot complete required groups.

Idle tests compare 64, 1,024 and 8,192 blocked requests in pure and mixed-wait workloads. The parent reads the worker's OS process CPU clock; candidate Python timing functions do not supply measurements. FCFS is checked through actual admission under capacity pressure, with no condition on dictionary insertion order or an Oracle helper. The real `EngineCore.step()` path covers polling when every live request awaits remote data, output recovery, completion and fresh admission. Cancellation, streaming, chunked prefill, backpressure and repeated preemption are included.

Resource tests use the same live scheduler for 1,310,720 sequential requests in each local/remote mode. Prompts vary from 32 to 64 tokens. All requests execute the production lifecycle, and the parent checks digests derived from actual per-request client tokens and terminal outputs against independently generated expectations. Normal empty ticks and GC permit batched cleanup. A native observer records live Python allocator bytes, including backing buffers, while excluding its own libc bookkeeping and avoiding nested-domain double counting. It has no reset/stop API. Fresh nonces and authenticated binary observations let the parent reject fabricated or replayed byte counts; replacing `tracemalloc` functions does not change measurements. This measures live allocation growth, not peak usage, allocator RSS or GPU memory.

The observer is not a sandbox against arbitrary native memory corruption or replacement of CPython allocators through native code. The verifier also does not prove correctness for every possible future workload. Those limits are separate from the exercised Python callback/global tampering, success-response forgery, false resource observations and early-exit controls.

Twelve required behavioral groups must finish, followed by normal worker shutdown, for reward 1. The known inherited block-ID leak and the heap alternative's retained version index are fixed in the reference patches. Historical implementations retaining either defect are negative controls; bounded caches, batched reclamation and reordered token-count mappings remain positive controls. Old callback and checkpoint-packet controls are retained as historical artifacts, and are superseded in active CI by controls for the new protocol.

## Evidence

[The evidence index](validation/e2e-evidence.json) records exact executable identities, actual results and remaining limitations. [The review](validation/review-report.md) and [remediation matrix](validation/remediation-matrix.md) map each finding to a behavior and control. Existing archives preserve older experiments; their scores are not v1.6.0 acceptance or new model rollouts. The numeric memory budget was introduced in v1.5.0 and must not be retroactively attributed to earlier statements.

Run through the normal task entrypoint with the pinned environment available:

```bash
harbor run -p tasks/vllm-remote-kv-idle-overhead -a oracle
```
