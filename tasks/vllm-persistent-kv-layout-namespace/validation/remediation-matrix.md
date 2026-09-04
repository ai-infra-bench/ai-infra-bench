# Remediation matrix

| ID | Finding | Approved resolution | Status |
|---|---|---|---|
| R1 | The statement broadened a V1-to-V2 rollout failure into every incompatible persistent layout. | Freeze the task around a gradual V1-to-V2 rollout, cross-runner isolation, same-runner restart reuse, and preservation of already-compatible sharing. | Complete |
| R2 | Rewarded tests injected `is_parallelism_agnostic` and did not execute the real V1/V2 configuration boundary. | Build V1 and V2 specs through `build_offloading_config` for the primary contract tests and real-filesystem E2E. | Complete |
| R3 | The public OPT model was absent from rewarded cases, so an implementation could deliberately exclude it and still receive reward 1. | Run both the public model identity and a hidden model identity; add an exclude-public-model adversarial control. | Complete |
| R4 | An always-miss implementation could avoid unsafe reuse by disabling useful cache hits. | Keep same-runner and compatible-sharing hit/data checks and add an always-miss adversarial control. | Complete |
| R5 | `[agent].timeout_sec` was 3600 rather than the project-required 36000. | Set the agent budget to 36000 seconds. | Complete |
| R6 | System packages and downloaded build tools are not fully pinned. | Leave the Dockerfile unchanged in this hardening pass. | Deferred by user |
| R7 | Existing evidence names an older instruction hash. | Do not treat the pre-existing mismatch as a blocker; refresh executable results and hashes only if validation evidence is rewritten in this pass. | Complete during final validation |

## Frozen semantic boundary

```text
V1 or V2 runner configuration plus a persistent cache root
-> real offloading configuration classification and filesystem namespace selection
-> an incompatible cross-runner lookup misses, while compatible restart data hits and loads intact
```

Model execution is a substitutable producer/consumer for this task. The real
configuration builder, `FileSystemTierManager`, asynchronous filesystem I/O,
block files, shutdown/reopen lifecycle, and cross-process persistence are the
behavior-determining components.
