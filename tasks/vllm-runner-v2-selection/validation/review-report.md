# Validation summary

Task 1.1.2: pooling hardening passed. The 22-case replay matrix matched expected rewards; the final Harbor Oracle completed 27/27 checks with reward 1 and no trial error. Early-exit and current-format report-forgery controls were rejected. Registry image publication remains pending.

| # | Review dimension | Score | Scope |
|---|---|---|---|
| 1 | Realistic, clear request | 2 | Existing developer query unchanged |
| 2 | Correctness independent of source PR | 2 | Oracle corrected against Base behavior |
| 3 | Solvable environment | 2 | Existing validated offline image |
| 4 | Bidirectional alignment | 2 | 27 representative startup cases |
| 5 | Real semantic path | 2 | Configuration → Worker → runner construction |
| 6 | Correct alternatives accepted | 2 | Six alternatives and Codex r2 pass |
| 7 | Incorrect solutions rejected | 2 | Base, old Oracle, r1/r3 and negative controls |
| 8 | Oracle independently challenged | 2 | Pooling support derived from Base |
| 9 | Grading integrity | 2 | Authenticated completion; not a native-code sandbox |
| 10 | Reproducibility and handoff | 1 | Evidence archived; registry pending |

10/10 dimensions assessed, 19/20. The statement/environment gates remain unchanged; the verifier gap is repaired. Tests cover startup, not weight loading or full generation, and do not exhaust all V2 combinations.

[Validation archive](validation-evidence.zip) contains detailed results, raw logs, historical reports, launchers and per-file hashes. Start with `records/pooling-evidence.json`; build notes are in `records/docker-build.md`. [Behavior mapping](semantic-boundary.md) and the CI control manifest remain outside the archive. Run `python3 .github/scripts/task_ci.py validate vllm-runner-v2-selection` from the repository root for static validation. Runtime replay commands and Harbor provenance are in the archive.

This commit only reorganizes evidence. The instruction, task metadata, environment, verifier and all control patches retain their validated contents; no GPU evaluation was rerun. Original rollout rewards remain historical results.
