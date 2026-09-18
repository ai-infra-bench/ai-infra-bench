# Review and validation: CPU-offload reset lifecycle (0.0.2)

Retain the task after hardening. The instruction remains unchanged and already
states the necessary public contract: the final benchmark request has ended,
store or load work can remain in flight, reset returns false until work settles,
old entries stay absent, and subsequent requests continue normally.

## Semantic boundary and environment

The required boundary is:

request finish with worker-owned store/load -> idle EngineCore continues polling
connector completion -> transfer references release -> connector reset succeeds
-> old cache miss and new store/load hit.

The real Scheduler, SimpleCPUOffloadConnector, SimpleCPUOffloadScheduler and CPU/
GPU BlockPool allocation state execute in the pinned image. Physical CUDA DMA is
replaced by a delayed process signal and a legal `KVConnectorOutput`; the real
request-finished, pending-work, completion and reset paths consume it. The
substitution preserves transfer cardinality, partial/out-of-order completion,
block ownership, event ordering and idle-engine liveness.

Base commit: `ed938ad7db9c28e3725058037c41285d8f46869e`.
Image: `sha256:7669d7a1375933c680aba58a378761db58776dc8f0aa61dcf3196df088df7ac7`.
Environment inputs and image were unchanged.

## Verifier behavior

The 30 scored cases cover eager/lazy stores and loads, one-to-three-block
prefixes, transfer-owned block pressure, idle and idempotent reset, old-hit
removal, delayed store suppression, reset_connector=false, out-of-order stores,
partial multi-worker completion, simultaneous store/load, five reset cycles,
post-reset reuse, and four final-request store/load liveness cases.

Transfer helpers now send `request_finished()` after a request has launched its
final transfer. Every liveness case requires both the connector standard hook
and `Scheduler.has_requests()` to remain true until completion. The composed
lifecycle checks the same boundary before its deterministic completion signal is
converted into real connector output.

A verifier-owned parent runs lifecycle code in a separate process session,
requires one exact completion record after every assertion, and kills the whole
session on incomplete termination. Candidate `SystemExit(0)` and `os._exit(0)`
therefore cannot convert missing checks into success.

## Oracle, alternatives and controls

The Oracle abandons pre-reset stores and loads while retaining their block
references, ignores stale completion data as cache content, and releases those
references only when completion arrives. Its pending-work hook includes active
and abandoned store/load state, partial worker counts and temporary hit pins.

Two semantically different correct alternatives are retained. One fails closed
until request and transfer state drains; the other uses explicit block-ownership
and stale-event guards. Both implement complete eager/lazy store/load liveness.
They and the Oracle pass an independent four-block-prefix challenge not present
in the scored width inventory.

Base, no-op, always-false, eager-only, early-reference-release, store-only
liveness, candidate-conftest skip, and two former no-liveness alternatives all
receive reward 0. `SystemExit(0)` and `os._exit(0)` also receive 0 after reaching
the real lifecycle reset boundary.

## Historical candidates and final Harbor matrix

The eight original gpt-5.6-sol patches were replayed unchanged. Attempts 1, 5,
7 and 8 receive 30/30 and reward 1. Attempts 2 and 6 fail the two load-liveness
cases. Attempts 3 and 4 fail all four store/load liveness cases. This preserves
their old records while providing the corrected classification for a versioned
rerun.

The final Docker matrix contains 14 cases and matches all expected rewards. The
final Harbor 0.22.0 matrix also contains 14 cases, matches all expected rewards,
and has zero Harbor exceptions. The final Oracle trial passes 30/30 with no
failures, errors or skips and completes the parent-attested lifecycle. Raw logs
are retained under `runs/cpu-offload-hardening-20260907-183000`.

## State

Task version is 0.0.2. Changes are local and uncommitted. No image rebuild,
push or PR was performed. Existing changes outside this task were not modified.
