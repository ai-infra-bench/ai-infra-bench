# Review remediation matrix

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person operational request contains no test, file, helper, or Oracle hints. | Complete |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked. | Complete |
| Behavioral / E2E boundary | The production Scheduler executes remote-KV blocking, idle ticks, completion promotion, mixed blocking reasons, FCFS order, accounting, and abort behavior. | Harbor Base/Oracle and controls complete |
| Implementation independence | The verifier observes production scheduler behavior through a contract-valid verifier-owned connector and delivers readiness through `update_from_output`; it no longer mutates an internal completion set that event-driven implementations may intentionally leave unpolled. Mixed FSM/remote/streaming waiters are covered without requiring a private queue name or repair location. | Complete |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | One private-queue-name alternative, one callback-only incomplete patch, and `SystemExit(0)`/`os._exit(0)` early-success controls were replayed through Harbor. | Expected rewards 1/0/0/0 observed |
| Calibration | After the completion-event fairness repair, Harbor Base/Oracle give 0/1 and direct final-image replay gives Base/Oracle/alternative/incomplete/SystemExit/os._exit=0/1/1/0/0/0. Two saved 1000-turn DeepSeek candidates that previously failed only because the verifier bypassed `update_from_output` now pass. | Complete |
