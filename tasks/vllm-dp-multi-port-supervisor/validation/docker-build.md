# Validation record

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

Validated on 2026-09-04 using the account-local Docker daemon at
`/root/workspace/dxz-workspace/.docker-dxz/run/docker.sock`. Runtime checks used
`--network none`; only loopback HTTP sockets were exercised.

## Source and image isolation

- vLLM base: `9b9d5dbaab852a1c615fe83a7f92881d353503db`
- accepted PR head: `d5ed61238528c4b753bceb761db91318b0d442fb`
- source tree: `94c86336cf2ea962766d00bb389d43a4d6aaf697`
- solution SHA-256:
  `7e11ade300c0991810ba59cf89e67574964d545a90adc82d37f768ae2a3a11d7`
- review image:
  `sha256:4de91d9731daf1348684397d24d3bd39d824eb1e3dea3d5e6a2c6cf28f530e3e`

The image runs as UID 1000 (`agent`). Its writable repository has one synthetic
commit, a clean worktree, and no Git remote. The Docker build context is only
`environment/`, so the instruction, verifier, and solution are not present in
the Agent image.

The Oracle is the complete production diff for the feature, excluding upstream
tests. It changes the CLI argument definitions and dispatch path, the API/log
integration, and the supervisor implementation. An earlier one-file Oracle was
discarded because it could not satisfy the public `vllm serve` contract.

## Behavioural controls

The hidden verifier starts the normal public CLI. A `sitecustomize` harness
replaces only heavyweight model serving with two lightweight loopback HTTP
servers and selects a deterministic CPU test platform because the verifier does
not reserve a GPU. Candidate CLI parsing, rank/port/device derivation,
multiprocessing, aggregate probes, monitoring, signal handling, and cleanup all
remain production code.

| Candidate | Expected | Observed | Reason |
|---|---:|---:|---|
| Locked Base | 0 | 0 | The public multi-port CLI is absent. |
| Complete accepted Oracle | 1 | 1 | All public and lifecycle checks pass. |
| Frozen Opus-5 round-one patch | 0 | 0 | It invents `--data-parallel-multiport` and `--multiport-dp-health-port`; the required CLI flags are unrecognized. |
| Renamed equivalent Oracle | 1 | 1 | Moving the module and renaming the supervisor class and private helpers still passes after public CLI rewiring. |

The accepted path checks:

1. overlapping supervisor/child ports fail before a server is left behind;
2. two consecutive child ports are opened and receive distinct per-rank device
   assignments;
3. aggregate `/health`, `/ready`, and `/readyz` remain 503 until both children
   are healthy, then become 200;
4. killing one child terminates its sibling and closes all three sockets;
5. a live child becoming unhealthy terminates the group;
6. SIGTERM to the supervisor is forwarded and leaves no rank or socket behind.

This is intentionally a frontend orchestration test. It does not claim to test
model loading, Kubernetes objects, multi-node routing, or inference throughput.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
