# DeepSeek V4 Flash hardening rollouts

On 2026-09-14, three Terminus-2 rollouts ran concurrently through Harbor against final image `sha256:714c9051899f5f88efaa7efeca4e42f6497d6daf076271f9bbd1ba3924d43883` with a 100-turn agent limit. All three trials completed without infrastructure errors or retries and scored 0. The job used 6,797,520 input tokens, 6,438,016 cached-input tokens, and 862,532 output tokens; the endpoint reported a total cost of `$0.090132224`.

| Trial suffix | Reward | Agent behavior | Verifier diagnosis |
| --- | ---: | --- | --- |
| `H38bq5s` | 0 | Investigated scheduler queues and remote-KV lifecycle but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 13.00. |
| `JL7Vn3a` | 0 | Investigated scheduler tests and request queues but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 12.93. |
| `PB35n37` | 0 | Investigated scheduler lifecycle and FCFS behavior but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 13.17. |

All three failures preserve the intended Base performance defect; none is a verifier rejection of an implemented alternative. The rollout review found agent non-convergence, not an instruction/verifier mismatch. No task repair was made solely to increase the model pass rate. The raw Harbor job is `pr61-deepseek-v4-flash-publication-r3` (job ID `cf637fa4-5bf8-4966-af2f-130673bb8e43`) under the local `runs/hardening-pr60-pr61` directory. Earlier attempts on pre-final image digests are retained there as superseded infrastructure/hardening evidence and are excluded from this frozen-version result.

## 2026-09-16 final 1000-episode calibration

After adding cancellation/completion races and staggered completion with a new
arrival, three fresh Terminus-2 trials ran concurrently through Harbor with
`openai/deepseek-v4-flash` and `max_turns=1000`. The frozen task checksum was
`f3a6b3dcbebf623889946757205b3eaf0ad41b8b04375551849c263258151795`.
All three trials completed without Harbor exceptions or retries and scored 1.

| Trial | Episodes | Reward | Candidate design and review result |
| --- | ---: | ---: | --- |
| `D25BJyV` | 637 | 1 | Split active and parked remote waiters while preserving the public queue facade; broad remote-KV, abort, ordering, and preemption tests passed. |
| `EVoY6jt` | 608 | 1 | Added a scheduler waiting-queue facade with event-driven promotion and stable FCFS keys; all seven authenticated checkpoints passed. |
| `iDuwE8i` | 484 | 1 | Added a combined queue with a separate remote-waiter map and event-driven promotion; focused and broader scheduler tests passed. |

The job used 45,575,458 input tokens, 43,605,376 cached-input tokens, and
4,662,386 output tokens; endpoint-reported cost was `$0.261632256`. Full patch
and trajectory review found three materially different event-driven designs and
no verifier false positive. A hypothesized queue-head/preemption interaction was
not added as a hidden test after source audit showed that preemption and waiting
allocation occur in separate production phases. The raw Harbor job is
`pr61-deepseek-v4-flash-auth-r5b-20260916` (job ID
`25f44faa-a97b-41de-b49e-3dbb6cade035`).

## 2026-09-16 strengthened-verifier rerun

Three further independent Terminus-2 trials ran concurrently through Harbor
with `openai/deepseek-v4-flash` and `max_turns=1000` against task version 1.1.4.
All three completed without Harbor errors, passed all eight authenticated
behavior/performance checkpoints, and scored `1/1/1`. The job
`pr61-deepseek-v4-flash-r3-enhanced` has ID
`0ef335c4-6505-4803-81fb-07713ddaeaa9`.

| Trial | Episodes | Reward | Code/trajectory review |
| --- | ---: | ---: | --- |
| `xfkdqfk` | 453 | 1 | Added an event-invalidated active waiting view in the scheduler; parked remote waiters remain visible for accounting, while idle ticks visit only active requests. |
| `kGXSyGd` | 668 | 1 | Added a combined waiting-queue facade with an active heap and event-driven remote reactivation; the agent also ran randomized queue checks. Its full pytest attempt was blocked by the base environment's missing `tblib`, but Harbor verification completed. |
| `QGr8Wd6` | 726 | 1 | Maintained active and logical queue views for FCFS/priority policies; the agent fixed a set-mutation bug found during its own review and ran queue smoke tests before grading. |

The endpoint reported 46,425,364 input tokens, 44,305,024 cached-input
tokens, 5,165,519 output tokens, and `$0.620270336` cost. Review of the
saved implementations did not identify a concrete contract violation or
verifier false positive. These are new runs, not replays of prior candidates.
