# Review remediation matrix

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person migration request supplies a normal TP/DCP/interleave configuration and changing-batch scenario, with no test, file, helper, or Oracle hints. | Complete in 1.4.0 |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked on H20. | Declared A100 runner replay pending |
| Behavioral / E2E boundary | Production runner initialization, real CUDA graph replay, eight successive scheduler outputs, and real sampling check token outputs in DCP eager/graph and non-DCP graph modes. Model arithmetic/attention consumption and rank metadata are deterministic substitutes. | Subsystem E2E on H20; not full distributed serving |
| Implementation independence | Removed signature-based graph argument injection. Real runner callers now own all DCP state/buffer propagation. Three different positive patches pass; saved candidate ReK9erk is no longer falsely rejected by a synthetic CpuGpuBuffer argument. | Complete in 1.4.0 |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | The parent scorer requires eleven ordered native authenticated checkpoints. Base, Oracle, three correct alternatives, one incomplete patch, and five bypass controls are replayed through Harbor. | See 1.4.0 matrix in e2e-evidence.json |
| Calibration | The most recent saved DeepSeek batch has raw 0/3 on 1.3.5 and frozen-candidate replay 1/3 on 1.4.0. This is distinct from the older 1/0/1 batch. | Original scores preserved; no new model rollout |
| Remaining environment evidence | Validation used H20, not the declared A100; complete upstream pytest readiness was not established this round. | Do not claim unconditional publication readiness |
