# Migration task review, v0.0.9

Retain after verifier repair. Two P1 scoring defects were reproduced and fixed; no new blocking statement or environment issue was found. The statement and Oracle are unchanged. This is task-level review and regrading of eight existing submissions, not a new sampling round or completion of the seven-task trajectory review.

| Finding | Before | After |
|---|---|---|
| Private catalog helper used to obtain fixture capacity | Equivalent rename: 36/38 component tests, 9/9 process tests, reward 0 | Frozen external capacity fixture; equivalent rename passes 41/41 and 9/9, formal reward 1 |
| Destination repricing not distinguished from source measurement | Incorrect source-budget implementation passes 38/38 and 9/9, reward 1 | High-source-usage case rejects that control for the intended defect; formal reward 0 |

The new repricing case records a source-route estimate of 4142 versus destination estimate 108. With output allowance 128, destination window 236 is an exact fit. Reusing the source estimate wrongly rejects it. Additional required cases cover Responses-only reasoning migrated into Chat after reopen, and returning to the source route with native replay preserved. Oracle passes all three.

Six formal Harbor controls completed with expected outcomes: Oracle, equivalent catalog refactor and alternative payload projection receive 1; Base, stale source budgeting and early successful exit receive 0. Each accepted control passes all 41 component cases and 9 real-process cases, with no skips. Five earlier Docker grading probes preserve the before/after counterexamples. Historical 18-control/19-Harbor evidence remains in v008-e2e-evidence.json and is not counted as new validation.

## Existing model submissions, regraded

These are identical final patches from the completed first-round matrix, applied through the formal artifact-transfer path. They are compatibility replays, not independent samples.

| Model / original trial | Components passed | Process cases passed | Reward |
|---|---:|---:|---:|
| g56-9FYgtuR | 35/41 | 7/9 | 0 |
| g56-BtnxTwV | 32/41 | 5/9 | 0 |
| g56-wEZZ6tX | 35/41 | 7/9 | 0 |
| g56-y24p9BH | 32/41 | 2/9 | 0 |
| g6-NFqqAeW | 38/41 | 8/9 | 0 |
| g6-TEQPsLJ | 38/41 | 8/9 | 0 |
| g6-TKPpb9E | 38/41 | 7/9 | 0 |
| g6-YVPVBWU | 38/41 | 8/9 | 0 |

## Scope and reproducibility

See v009-behavior-map.md for the contract-to-observation map. The process tests execute real CLI/Remote, SDK, bash tools, persistence and cold Host recovery; deterministic HTTP substitutes only generation. Source IDs are opaque strings at the custom gateway boundary, and tests do not require a particular destination ID spelling. Independent environment audit reconfirms the exact Base, clean source and absence of Git remotes, tags, reflogs, unreachable objects and task mounts.

Finite tests establish the listed properties, not universal correctness or resistance to every candidate attack. No commit or push was made. Worktree: /home/tiger/lidailin/ai-infra-bench, branch main. The next independent 56-run matrix remains gated on completion of the whole first-round review.
