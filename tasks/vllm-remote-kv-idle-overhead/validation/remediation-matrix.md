# Review remediation matrix

## Current repair: 1.3.0

See [the current review](repair-review-2026-09-17.md) and
[actual repair controls](repair-calibration-2026-09-17.json). The old streaming
fixture rejected event-driven solutions; the old Oracle starved mixed streaming
continuations and the old alternative retained linear mixed-idle work. Those
findings are repaired, with both flawed references retained as negative controls.
LLaVA metadata is now pinned for ordinary offline tests. Twelve Harbor controls
matched expectations, but final trust review and fresh model trials are pending.
The following table describes the earlier 1.2.x iteration, not current acceptance.

## Historical 1.2.x record

| Review finding | Remediation | Current state |
| --- | --- | --- |
| Meaningful task identity | Uses the descriptive task directory and task name. | Complete |
| Human task statement | First-person idle-CPU report includes A/B remote waits, local C, and out-of-order transfer readiness, without internal repair hints or a public test script. | Complete in 1.2.0 |
| Environment isolation | The final Dockerfile was built from a read-only local source mirror; exact Base/tree, reachable history, clean worktree, no remotes/tags/reflogs/unreachable objects, import path, absent curator artifacts, agent identity, and no-network runtime were checked. | Complete |
| Behavioral / E2E boundary | Real Scheduler admission through client token streams and normal finish, including chunked prefill, readiness, capacity pressure, later arrivals and no-connector regression; previous idle/cancellation/FCFS tests retained. | Subsystem E2E; model/transport deterministic substitutes |
| Implementation independence | The verifier observes production scheduler behavior through a contract-valid verifier-owned connector and delivers readiness through `update_from_output`; it no longer mutates an internal completion set that event-driven implementations may intentionally leave unpolled. Mixed FSM/remote/streaming waiters are covered without requiring a private queue name or repair location. | Complete |
| Harbor alignment | 10-hour Agent budget, offline phases, separate verifier, explicit artifacts, accelerator/workdir metadata, and verifier mount. | Static validator passes |
| Controls | Eleven ordered native authenticated checkpoints. Base, Oracle, different positive implementation, incomplete patch, output-loss mutant, and five bypass controls replayed through Harbor. | Dropped-client-output mutant: old verifier 1, new verifier 0 |
| Calibration | The three most recent saved DeepSeek candidates pass the final 1.2.0 verifier without code changes. | Historical candidate replay, not new model rollout |
| Agent upstream test readiness | The final image's scheduler pytest collection fails before tests because tblib is absent. Hidden tests work; these are different claims. | Dependency/image repair and upstream smoke remain pending |
