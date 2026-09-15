# DeepSeek V4 Flash hardening rollouts

On 2026-09-14, three Terminus-2 rollouts ran concurrently through Harbor against final image `sha256:b8a1ddd7e3a2c075f8ae106088c7f5c89e9dc28ec922e5fc2f43b7d6ce0adf15` with a 100-turn agent limit. All three trials completed without infrastructure errors or retries and scored 0. The job used 10,831,553 input tokens, 10,488,064 cached-input tokens, and 282,971 output tokens; the endpoint reported a total cost of `$0.146832896`.

| Trial suffix | Reward | Agent behavior | Verifier diagnosis |
| --- | ---: | --- | --- |
| `HbgAyrH` | 0 | Correctly identified the missing V2 DCP metadata, slot-mapping, and graph paths, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |
| `VYNcmP8` | 0 | Investigated legacy/V2 metadata and block-table behavior, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |
| `eDyy5Bd` | 0 | Mapped the relevant runner, block-table, and CUDA-graph call sites, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |

All three failures are agent non-convergence after accurate reconnaissance, not verifier rejections of plausible implementations. They fail at the intended Base behavior, and no wrong reward or verifier-driven repair was identified. The raw Harbor job is `pr60-deepseek-v4-flash-publication-r3` (job ID `1ca43345-b357-4a7c-9ed0-a06d8b8f2669`) under the local `runs/hardening-pr60-pr61` directory. Earlier attempts on pre-final image digests are retained there as superseded infrastructure/hardening evidence and are excluded from this frozen-version result.
