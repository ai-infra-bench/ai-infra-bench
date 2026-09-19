# Real-agent rollout 4, 2026-09-16: claude-code + claude-opus-5 on the 0.0.3 instruction (local, linux/arm64)

| Item | Value |
|---|---|
| Agent | Harbor `claude-code` (subscription OAuth token, host proxy) |
| Model | claude-opus-5, agent timeout multiplier 0.15 (90 min); finished on its own in 32 min (13:10Z to 13:42Z) |
| Trajectory | 121 tool calls (81 Bash, 20 Edit, 11 Write, 9 Read) |
| Submission | `examples/extensions/background-processes/{index,tools,manager,log-store,bash-tool,types}.ts` + README, plus `docs/extensions.md` and the examples README; one new unit test file, no existing test touched |
| Job | `~/ai-infra-scratch/harbor-jobs/rollouts/pi-background-processes--claude-code--claude-opus-5--x0.15--20260916-211021` |
| Reward | **0** |

## Verifier result as recorded (harness before the 0.0.4 revision)

| Layer | Result |
|---|---|
| PASS_TO_PASS | pass |
| Contract | 10/15: four cases died at the verifier's own `AgentSession.prompt` with "Agent is already processing", one (`bash` stall) returned a tool error |
| Lifecycle | 2/3: "SIGTERM to the pi process stops managed processes" timed out |

## What was really wrong (reproduced)

Every failing contract case passes alone. In the suite:

1. **Harness spill-over, not a defect (four cases).** The submission reports a process's
   exit only after its pipes have been idle for 100 ms and batches wake reasons for 10 ms.
   The verifier's between-test drain ran one `bg_list` prompt and disposed the session
   before that wake landed; the manager, seeing no active session, kept the wake and
   delivered it to the next test's session with a triggered turn, exactly as the contract
   says ("otherwise to the current active session"; "while idle, the wake starts a new turn
   immediately"). The next test's first prompt then hit a busy agent. Fixed in the harness
   (0.0.4): the drain waits 300 ms and for an idle session, and a verifier prompt waits
   for an idle session first. Under the revised harness these four cases pass.
2. **Genuine defect: the auto-background path breaks after a reload.** The manager lives
   on `globalThis` so it survives `/reload`, but the `bash` override recognises a
   backgrounded command with `instanceof BackgroundedError`, and a re-loaded extension
   module has a new class identity. In any session after the first (a `/reload`, or the
   verifier's second session in one process) the stalled command produces a tool error
   `Command moved to the background after 1s without output` instead of the record. The
   contract: "From then on the process is exactly like one started with `bg_run`" and
   "`/reload` ... must not stop them".
3. **Genuine defect: SIGTERM never ends pi.** The signal handler starts with
   `if (process.listenerCount(signal) > 1) return;`, deferring to "someone else (pi
   itself)". In a headless pi the other listener is `signal-exit` from pi's dependency
   tree, which also defers, so nobody terminates the process. Same clause as grok
   rollouts 2 and 3; the 0.0.1 opus rollout, which had the mechanism hint, re-raised
   unconditionally and passed. 0.0.4 restates the clause as an unmistakable outcome
   ("interactive or headless ... never keeps running") without naming a mechanism.

Verdict: reward 0 stands on two real defects; the four spill-over failures were a harness
fragility and are fixed. The submission is kept as the expected-0 control
`alt-opus-0.0.3-defer-and-reload.patch` (contract 14/15 and lifecycle 2/3 under the revised harness).
