# vLLM remote-KV idle scheduling

Keep idle scheduler ticks independent of unchanged remote-KV waiters while preserving FCFS, request accounting, cancellation, generation, completion and later admission. The task also requires progress under limited KV capacity, NIXL full-local-hit progress despite producer notification failure, and the explicit retained Python memory budget in [instruction.md](instruction.md).

## Environment and boundaries

The exact Base source, pinned CPU donor, offline public model metadata and 36,000-second agent budget are unchanged. The production scheduler, EngineCore, KV manager and NIXL connector scheduler/worker execute for real. Model arithmetic and transport availability are controlled inputs. NIXL's external IO agent is substituted at its package API with an in-memory CPU implementation; actual vLLM registration, metadata construction, loopback ZMQ handshake, transfer dispatch and completion collection remain in production code. No GPU/RDMA throughput or full model quality claim is made.

## Verification

The root-owned parent never imports candidate vLLM. It checks request operations and client results, reads the worker's OS CPU clock, and authenticates native Python allocator observations. It starts with `-I -S`; candidate site packages load only in the unprivileged worker. The native observer has no reset API and does not take measurements from candidate Python timing or tracemalloc functions. This covers the exercised Python-level attacks, without claiming a native-memory sandbox.

Fourteen behavioral groups cover pure/mixed idle scaling, real EngineCore lifecycle, cancellation races, FCFS across blocked reasons, streaming, capacity pressure, preemption, KV-space pressure, NIXL prefix/notification lifecycle and both long-run memory modes. Token maps are compared by identity; FCFS is observed through admission, without a prescribed queue, helper, reservation field or placeholder representation.

KV-pressure cases vary cache size, prefix coverage, prompt length and generation budget. They include one-request and roomy-pool controls, multiple async loads, local decode competing with a load, cancellation before/after receive completion, and subsequent admission. Completion events are produced only for transfers that the connector actually started. Tests require correct client outputs and eventual completion, not a specific number of simultaneous loads or reservation algorithm.

NIXL coverage combines its stable connector API with real KV allocation and EngineCore execution. A local prefix is populated by real scheduling; a full-prefix lease is established for the request before its post-allocation connector callback, then rolled back before ordinary engine admission. The frozen scheduler may recompute final logits. No private request status or modern `awaiting_kvs` field is manufactured. Tests cover notification success/failure, cancellation notification without request revival, and non-empty receives through the real completion collector. A normal receive primes the connection so notification fault injection is not bypassed by handshake timing. The decision flags and notification counts are diagnostic; final request outcomes determine correctness.

The published later NIXL fix #56640 distinguishes parked receives from notification-only work. On the frozen Base, the full-local-hit API follows the notification-only path and already progresses on notification failure. This revision adds verified regression coverage and targeted broken controls rather than importing a later, unproven parked state into the older version.

Resource tests retain the long-lived scheduler for 1,310,720 requests in each local/remote mode, with earlier samples catching larger leaks promptly. The native observer measures current Python allocations beyond warm-up, not RSS, peak or GPU memory. Bounded caches and batched cleanup are positive controls. Harbor allows 7200 seconds for verification; the scoring supervisor has a separate 900-second internal deadline.

## References and evidence

The reference implementations reserve admission capacity for already admitted requests and reclaim those reservations on completion/preemption/cancellation. They remain different scheduler representations: an event-ready queue implementation and a heap implementation. This is one repair strategy, not a grader requirement.

Keep actual results, scope, image identity, hashes, and limitations with the corresponding CI or Harbor run records. Historical review reports remain available in Git history; each result applies only to its recorded snapshot, and replays are not new model rollouts.

```bash
harbor run -p tasks/vllm-remote-kv-idle-overhead -a oracle
```
