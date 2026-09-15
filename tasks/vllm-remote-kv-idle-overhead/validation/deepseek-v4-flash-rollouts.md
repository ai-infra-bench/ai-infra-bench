# DeepSeek V4 Flash hardening rollouts

On 2026-09-14, three Terminus-2 rollouts ran concurrently through Harbor against final image `sha256:714c9051899f5f88efaa7efeca4e42f6497d6daf076271f9bbd1ba3924d43883` with a 100-turn agent limit. All three trials completed without infrastructure errors or retries and scored 0. The job used 6,797,520 input tokens, 6,438,016 cached-input tokens, and 862,532 output tokens; the endpoint reported a total cost of `$0.090132224`.

| Trial suffix | Reward | Agent behavior | Verifier diagnosis |
| --- | ---: | --- | --- |
| `H38bq5s` | 0 | Investigated scheduler queues and remote-KV lifecycle but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 13.00. |
| `JL7Vn3a` | 0 | Investigated scheduler tests and request queues but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 12.93. |
| `PB35n37` | 0 | Investigated scheduler lifecycle and FCFS behavior but reached 100 turns with a clean worktree. | Idle-work scaling ratio remained 13.17. |

All three failures preserve the intended Base performance defect; none is a verifier rejection of an implemented alternative. The rollout review found agent non-convergence, not an instruction/verifier mismatch. No task repair was made solely to increase the model pass rate. The raw Harbor job is `pr61-deepseek-v4-flash-publication-r3` (job ID `cf637fa4-5bf8-4966-af2f-130673bb8e43`) under the local `runs/hardening-pr60-pr61` directory. Earlier attempts on pre-final image digests are retained there as superseded infrastructure/hardening evidence and are excluded from this frozen-version result.
