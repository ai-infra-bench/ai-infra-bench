# DeepSeek V4 Flash hardening rollouts

Version clarification: the original rollout records below remain unchanged. Regrading the latest enhanced batch on verifier 1.4.0 gives ReK9erk/jQwFCvS/sL3ZB4M = 1/0/0, not its original 0/0/0. The first failure was a synthetic graph-buffer fixture mismatch. See [the new review](instruction-e2e-review-2026-09-16.md); this regrade is not a new model rollout and must not be conflated with earlier three-trial batches.

On 2026-09-14, three Terminus-2 rollouts ran concurrently through Harbor against final image `sha256:b8a1ddd7e3a2c075f8ae106088c7f5c89e9dc28ec922e5fc2f43b7d6ce0adf15` with a 100-turn agent limit. All three trials completed without infrastructure errors or retries and scored 0. The job used 10,831,553 input tokens, 10,488,064 cached-input tokens, and 282,971 output tokens; the endpoint reported a total cost of `$0.146832896`.

| Trial suffix | Reward | Agent behavior | Verifier diagnosis |
| --- | ---: | --- | --- |
| `HbgAyrH` | 0 | Correctly identified the missing V2 DCP metadata, slot-mapping, and graph paths, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |
| `VYNcmP8` | 0 | Investigated legacy/V2 metadata and block-table behavior, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |
| `eDyy5Bd` | 0 | Mapped the relevant runner, block-table, and CUDA-graph call sites, but reached 100 turns with a clean worktree. | Base rank-local slot mismatch remained. |

All three failures are agent non-convergence after accurate reconnaissance, not verifier rejections of plausible implementations. They fail at the intended Base behavior, and no wrong reward or verifier-driven repair was identified. The raw Harbor job is `pr60-deepseek-v4-flash-publication-r3` (job ID `1ca43345-b357-4a7c-9ed0-a06d8b8f2669`) under the local `runs/hardening-pr60-pr61` directory. Earlier attempts on pre-final image digests are retained there as superseded infrastructure/hardening evidence and are excluded from this frozen-version result.

## 2026-09-15 1000-episode fairness audit

Three new Terminus-2 trials used `openai/deepseek-v4-flash`, 1000 maximum
episodes, the same final image, and the authenticated eight-checkpoint scorer.
All three reached the episode limit without infrastructure errors. The original
verifier recorded `0/0/0`, each at checkpoint 6 with "CUDA-graph attention
metadata omitted DCP-local lengths". The job consumed 111,511,617 input,
107,897,216 cached-input, and 4,661,524 output tokens; endpoint-reported cost
was `$1.510561024`.

Trajectory review found that this common score hid two different outcomes. One
candidate truly omitted the graph-capture connection. Two candidates correctly
carried DCP-local lengths through different production designs, but the fixture
called their extended helper or buffer constructor with non-DCP defaults. The
verifier now supplies semantic DCP arguments when those production boundaries
accept them, while retaining the Oracle's group-derived path.

| Trial | Episodes | Original reward | Corrected replay | Diagnosis |
| --- | ---: | ---: | ---: | --- |
| `8uG2X9e` | 1000 | 0 | 1 | Valid explicit model-runner → graph-capture buffer/coordinate flow; old fixture omitted its optional DCP arguments. |
| `MaRCMEt` | 1000 | 0 | 0 | Eager metadata was wired, but graph-input preparation remained incomplete. |
| `SFayF95` | 1000 | 0 | 1 | Valid DCP-aware `InputBuffers` design; old fixture constructed it with non-DCP defaults. |

The corrected verifier was replayed through Harbor against Base, Oracle, both
new correct candidates, the truly incomplete candidate, the existing correct
alternative, the existing incomplete implementation, and all five bypass
controls. Rewards were respectively `0/1/1/1/0/1/0/0/0/0/0/0`, with no Harbor
exceptions. Original trial artifacts and rewards remain unchanged; the corrected
values are separate frozen-patch replays under `pr60-fairness-v2-*`.

## 2026-09-16 final 1000-episode calibration

After strengthening CUDA-graph replay to mutate request order, request splits,
and positions across replays, three fresh Terminus-2 trials ran concurrently
through Harbor with `openai/deepseek-v4-flash` and `max_turns=1000`. The frozen
task checksum was
`1e943dde68ddf037d6ae7403cbdc8cbf9708c373c2b03c1ab231aeb010f1934f`.
All three trials completed without Harbor exceptions or retries; rewards were
`0/1/0`.

| Trial | Episodes | Reward | Verifier diagnosis |
| --- | ---: | ---: | --- |
| `CSdpUHn` | 1000 | 0 | Candidate changed the attention initialization return contract; production initialization failed with `expected 3, got 2` before the slot checks. |
| `M7fmhHn` | 1000 | 1 | Candidate completed all eight authenticated checkpoints, including held-out ranks, multiple cache groups, mutable CUDA-graph replay, and successive graph metadata. |
| `qP84ifA` | 1000 | 0 | Candidate rejected a contract-valid KV-cache spec during production initialization with `NotImplementedError`; only preflight completed. |

The job used 110,667,768 input tokens, 106,960,128 cached-input tokens, and
4,801,124 output tokens; endpoint-reported cost was `$0.641760768`. The two
failures are candidate implementation regressions rather than verifier or
environment failures. The raw Harbor job is
`pr60-deepseek-v4-flash-auth-r5b-20260916` (job ID
`3090e05f-220b-4776-b77c-f9b118a4162e`).

## 2026-09-16 strengthened-verifier rerun and fixture correction

Three more independent Terminus-2 / `openai/deepseek-v4-flash` trials ran in
parallel against task version 1.3.5 with `max_turns=1000`. All reached the turn
limit and completed Harbor verification without infrastructure errors. The raw
rewards were `0/0/0` (job `pr60-deepseek-v4-flash-r3-enhanced`, ID
`c67555b5-cd65-4cbe-84aa-567b50d8c253`). The endpoint reported 116,415,304
input tokens, 112,787,712 cached-input tokens, 4,250,541 output tokens, and
`$1.579027968` cost.

| Trial | Original checkpoints | Final 1.3.6 candidate replay | Diagnosis |
| --- | ---: | ---: | --- |
| `jQwFCvS` | 3/9 | 0 | DCP interleave size was not passed from the production runner to `BlockTables`; the slot calculation used the default of 1. |
| `sL3ZB4M` | 2/9 | 0 | The old synthetic `model_config` lacked the production `use_mla` property, masking a later real omission of DCP-local lengths in CUDA-graph attention metadata. With the fixture corrected, the candidate reached 7/9 before failing there. |
| `ReK9erk` | 7/9 | 0 | Graph capture indexed a `CpuGpuBuffer` as though it were subscriptable, causing a candidate-side `TypeError`. |

Task version 1.3.6 adds `use_mla=False` to the synthetic configuration. On
that final snapshot, fresh Harbor Base, Oracle, correct alternative, and
incomplete-implementation controls returned `0/1/1/0`. The three *saved*
candidate repositories were then replayed against the corrected verifier;
those replays do not constitute new model trials and all still score zero.
