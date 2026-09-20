# Remediation matrix — v1.7.0

| Finding / requirement | Change | Verification |
|---|---|---|
| Competing async loads deadlock when each request fits independently | Reference admission accounts for already promised KV capacity and its own remaining request budget | Limited/roomy/single-request cases, varied lengths and decode budgets, mixed local/remote, cancellation and fresh admission |
| Test must not force the reservation algorithm | Grade progress, tokens, terminals and request counts; completion events follow actual receive starts | Queue and heap references plus representation/cache positives |
| NIXL full-local-hit requirement needs a real connector path | Execute production NIXL scheduler/worker, registration, handshake, dispatch and completion collection | Success/failure notification, cancellation and normal receive through EngineCore |
| Do not invent a later parked state on the frozen Base | Use the documented full-local-hit connector input; establish an actual KV allocation lease; no private state injection | Isolated NIXL regression also passes on Base |
| A naive NIXL fix may report harmful or missing completions | Deliver actual connector results to real scheduler output handling | Spurious completion, dropped completion, notification exception and stalled-notification controls |
| Existing v1.6 integrity/performance/resource fixes must remain | Parent-owned assertions/timing, authenticated allocator observations, long-lived request tests | Full current control manifest, with resource/integrity mutations rebased to preserve intended failure causes |
| Evidence must match actual execution | Frozen executable hashes and separate records for reduced development probes, full scoring, challenges and Harbor | Current evidence index and raw archive |

The two added statement sentences were approved before tests and reference changes. No MTP, real RDMA throughput or private helper/metadata representation is added as a hidden requirement.
