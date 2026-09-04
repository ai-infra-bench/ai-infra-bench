# Remediation matrix

| Finding | Resolution | Status |
|---|---|---|
| F1: shared root verifier can replace Python | Run the agent as `agent`, transfer only `/workspace/vllm/vllm`, and verify in a fresh root-owned container with tests mounted read-only. The interpreter-tamper Harbor control receives reward 0. | Closed |
| F2: instruction contains non-Base and anonymized logs | Replace the logs with a validated infrastructure-investigation workflow and behavior-level observations. | Closed |
| F3: environment contains post-cutoff components | Pin Python 3.12.12 and Dockerfile frontend digests, use the 2026-03-24 Debian snapshot, pin uv 0.11.0 by wheel hash, and remove unused Rust/nextest. | Closed |
| F4: HTTP test is only a generic regression | Use a real streaming `vllm serve` contention workload and observe completion events, preemption metrics, and relative decoder gaps. | Closed |
| F5: verifier requires zero preemption | Permit one necessary preemption while rejecting repeated rollback of the same request. | Closed |
| F6: full-ISL Oracle over-serializes recyclable attention | Use the startup pool-sizing bound for sliding-window and chunked-local attention and test full, sliding, chunked-local, and hybrid groups. | Closed |
| F7: no semantically different correct alternative | Add a scheduler-side reservation implementation that differs from the KV-manager-centered Oracle and receives reward 1. | Closed |
| F8: evidence hashes and Harbor results are stale | Refresh executable hashes, five-round results, all controls, image identity, and final Harbor identifiers. | Closed |
| F9: one-hour agent timeout | Set `[agent].timeout_sec` to `36000`. | Closed |
