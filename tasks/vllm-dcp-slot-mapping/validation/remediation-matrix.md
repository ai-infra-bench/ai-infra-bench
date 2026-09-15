# Review remediation matrix

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person operational request contains no test, file, helper, or Oracle hints. | Complete |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked on H20. | Declared A100 runner replay pending |
| Behavioral / E2E boundary | Production Model Runner initialization, DCP-aware slot mapping, real CUDA graph replay, and graph attention metadata are exercised on an NVIDIA H20. | Harbor Base/Oracle and controls complete |
| Implementation independence | Exact block-table-width grading was removed, and the model runner now enters through its real constructor rather than a partially initialized `__new__` object. A materially different correct implementation passes while eager-only and graph-incomplete implementations fail on behavior. | Complete |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | One production-only alternative, one incomplete patch, and `SystemExit(0)`/`os._exit(0)` early-success controls were replayed through Harbor. | Expected rewards 1/0/0/0 observed |
| Calibration | After the constructor-fairness repair, direct final-image replay gives Base=0, Oracle=1, alternative=1, incomplete/SystemExit/os._exit=0/0/0. The three saved 1000-turn DeepSeek candidates also remain 0 because their graph-metadata behavior is incomplete, rather than because candidate constructor state was skipped. | Complete |
