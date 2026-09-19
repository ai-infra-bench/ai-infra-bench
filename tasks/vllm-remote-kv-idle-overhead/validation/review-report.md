# PR #61 — KV pressure and NIXL behavior, v1.7.0

This revision implements the two user-approved statement additions and adds independent behavior coverage. The reference scheduler and heap alternative now handle competing async loads under limited KV capacity. NIXL receives regression coverage through its production connector code; its frozen full-local-hit behavior is distinguished from later upstream parked-receive changes.

## Statement and source boundary

The statement adds only: requests should finish under tight KV space when each can fit independently, and NIXL full-local-hit requests should continue whether producer notification succeeds or fails. It does not prescribe an admission policy, reservation field, receive marker or helper. The original idle, FCFS, cancellation, output and 32 MiB retained-memory requirements remain.

Upstream #44560 motivates the cache-pressure challenge. On the pinned Base, the earlier Oracle and heap both stalled with two 64-token prompts, 32 remotely loaded tokens per request and five usable blocks. Each request needed four blocks on its own. One request or a larger pool completed, establishing a real resource-competition defect rather than an impossible input. Later upstream #57104 concerns MTP lookahead and is not made into an extra hidden task requirement.

Upstream #56640 must not be copied blindly: it distinguishes parked receives from notification-only operations. The pinned NIXL connector's full-local-hit API already chooses a no-receive path. The new isolated NIXL behavior run therefore legitimately passes on Base as well as both references. No later `awaiting_kvs` field, private request status or receive dictionary is injected into this version. The reference changes for this revision are in the scheduler and KV allocator; there is no unsupported claim that a later NIXL production fix was backported.

## Real execution and substitutions

KV-pressure cases enter through real EngineCore, Scheduler and KV manager behavior. The minimal test connector records actual receive starts through its normal allocation callback; readiness is supplied only for those initiated loads. Outcomes are generated tokens, terminal events, request counts, progress and subsequent admission. No private reservation container or particular order of starting async loads determines reward.

The NIXL case runs the real vLLM connector scheduler and worker, real CPU cache allocation/registration, real loopback ZMQ handshake, metadata generation, read/notification dispatch and completion collection. It substitutes the external `nixl._api` transport agent, before candidate imports, with a fixture that moves registered CPU buffer data and can fail notifications. This supports ordinary import styles without replacing a vLLM helper or completion function. No native NIXL/RDMA or model-quality claim is made.

A normal receive primes the connection before notification fault injection. The full-local-hit component boundary receives a real cached prefix and a real allocation lease for that request. The lease is rolled back before normal EngineCore admission; the pinned scheduler can recompute final logits. This is composed behavior coverage of the documented connector input and downstream lifecycle, not a claim that the old scheduler naturally constructs a later-version parked empty receive. Decision flags and notification counts are diagnostic only; client progress/output and request lifecycle decide reward. Cancellation-before-start and a subsequent non-empty receive protect against unconditional or missing completion reports.

The parent still owns all assertions, expected outputs, CPU measurements, authenticated allocation observations and reward. It never imports candidate vLLM. The 14 required groups include the original 12 plus KV pressure and NIXL prefix lifecycle. The 900-second deadline accommodates legitimate long-run cleanup and the added production path without making successful runs wait.

## Coverage and controls

| Contract | Behavior exercised | Relevant control |
|---|---|---|
| Each request fits, but combined async loads may not | Six cache/prompt/prefix/budget combinations, single/roomy controls, mixed local decode and remote load | Prior Oracle restored as `kv-load-deadlock` |
| Cancellation remains correct under pressure | Abort before/after receive completion; deliver late events; survivor finishes and capacity remains usable | Existing cancellation regressions plus new pressure cases |
| Full local NIXL hit keeps progressing | Producer notification succeeds/fails; actual client token and terminal output, drained request counts | `nixl-noop-stall`, `nixl-notification-exception` |
| Cancellation does not revive requests | Production notification-only metadata from cancellation, then fresh admission | `nixl-spurious-completion` |
| Ordinary NIXL receives still resume | Real non-empty worker receive and completion collector feed EngineCore | `nixl-dropped-completion` |
| Internal representation remains free | Queue and heap references, reordered token maps, bounded history and batched cleanup | Five positive implementations/variants |
| Existing performance/resource/integrity contract remains | Original idle, lifecycle, preemption, resource and tampering cases | Rebased resource/integrity controls retain their intended first failure |

The references use a constant-time reservation total updated when admitted requests allocate, finish, cancel or are preempted. Admission checks the remaining full request budget as well as existing commitments, preventing over-promising to several partially loaded requests. This is a conservative implementation choice; tests accept other methods producing the required behavior. Idle fixtures provide enough cache for the requested population so they compare the same waiting condition at each scale.

A separate challenge varies cache capacity, prompt lengths, chunk budgets, decode budgets, identities and local/remote combinations across twelve workloads per reference. It is separate from the scored suite. The NIXL-only check on Base is also separate from full scoring: Base must still receive 0 on the task's original idle defect.

## Evidence and limits

Actual final-snapshot results, first failure reasons, runtime and executable identities, independent challenges and Harbor trials are in [e2e-evidence.json](e2e-evidence.json). Earlier v1.6 records are retained in `hardening-v160.zip` and the history archive, without changing historical scores. New replays are not new LLM capability experiments.

Environment inputs remain unchanged. Local validation uses the previously verified exact Base source tree and pinned CPU donor in diagnostic image `sha256:5e0979545d33f27080023c5fc18d30e3f0182732f6912b1b3b404cde475b81e7`. Its synthetic Git history differs from the canonical task image; results explicitly identify this distinction. The remote v1.6 CI success does not certify the newer v1.7 executable snapshot. The native allocation observer is not a sandbox against arbitrary native memory/allocator replacement, and finite test populations are not a proof for every future workload.

## Completed local validation

All 27 final-snapshot scoring replays matched their expected rewards: five positive implementations/variants completed 14/14 groups, and twenty-two negatives were rejected. Nine actual Harbor 0.22.0 trials completed with zero framework errors; Oracle and heap received 1, and all seven integrity/new-behavior negatives received 0. Each pressure challenge passed twelve workloads on both reference implementations. The isolated NIXL regression passed on Base, Oracle and heap; it is not a claim that Base passes the full task.

Raw records and first failures are in `hardening-v170.zip`. Local work used the exact-source diagnostic image identified below, without changing the task's canonical environment inputs. The executable snapshot is identified by file hashes and the pre-change task commit `bc3810a15a871d682fcb655cf6a4bf8823ce2aa8`; evidence-only writes occur after those runs.
