# Review remediation matrix

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person operational request contains no test, file, helper, or Oracle hints. | Complete |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked on H20. | Declared A100 runner replay pending |
| Behavioral / E2E boundary | Production Model Runner initialization, DCP-aware slot mapping, real CUDA graph replay, and graph attention metadata are exercised on an NVIDIA H20. | Harbor Base/Oracle and controls complete |
| Implementation independence | Exact block-table-width grading was removed, the model runner enters through its real constructor, and graph fixtures support both group-derived state and production callers that explicitly pass DCP buffers/coordinates. Three materially different correct implementations pass while eager-only and graph-incomplete implementations fail on behavior. | Complete |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | The parent scorer requires eight ordered native checkpoints authenticated with a key unavailable to candidate Python. Three correct alternatives, two incomplete patches, `SystemExit(0)`, `os._exit(0)`, forged stdout, forged checkpoint, and callback theft were replayed through Harbor. | All correct variants scored 1; Base, incomplete, and bypass variants scored 0; 0 exceptions |
| Calibration | Harbor Base/Oracle give 0/1 on the final verifier. Frozen replay of the three 1000-episode DeepSeek candidates gives 1/0/1 after correcting fixture coupling; the remaining failure is a genuine missing graph connection. | Complete |
