# Review remediation matrix

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person operational request contains no test, file, helper, or Oracle hints. | Complete |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked. | Complete |
| Behavioral / E2E boundary | The production Scheduler executes remote-KV blocking, idle ticks, completion promotion, mixed blocking reasons, FCFS order, accounting, and abort behavior. | Harbor Base/Oracle and controls complete |
| Implementation independence | The verifier observes production scheduler behavior through a contract-valid verifier-owned connector and now covers mixed FSM/remote/streaming waiters without requiring a private queue name or repair location. | Complete |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | One private-queue-name alternative, one callback-only incomplete patch, and `SystemExit(0)`/`os._exit(0)` early-success controls were replayed through Harbor. | Expected rewards 1/0/0/0 observed |
| Calibration | On the final image Base=0, Oracle=1, alternative=1, incomplete/SystemExit/os._exit=0/0/0. Three DeepSeek V4 Flash rollouts on the same frozen snapshot all scored 0 after making no source change, with no Harbor errors. | Complete |
