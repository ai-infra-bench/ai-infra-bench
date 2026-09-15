# Task review — 2026-09-14

Verdict: the task can be retained; its statement and verifier gates pass on the final rebuilt image, while publication awaits replay on the declared A100 runner. Review snapshot: PR #60 base `345a275c5971f9df527f8648509f03650980a193` plus the uncommitted hardening diff; Base `be3af2d29e2507f32b2190fe015cd6609b348caa`; review skill from official `main` on 2026-09-14.

| # | Dimension | Score / status | Key evidence or gap | Next action |
| ---: | --- | --- | --- | --- |
| 1 | Is the task realistic and clear? | 2 | One-paragraph first-person request describes observable DCP eager/graph behavior without file or test hints. | None. |
| 2 | Is correctness independent of the source PR? | 2 | Contract is behavioral; the Oracle is not named or prescribed. | None. |
| 3 | Can the agent solve the task in the environment? | 2 | The final Dockerfile rebuild exposes the exact clean Base to the declared agent user with terminal/test tooling and no curator artifacts or future Git source. | None. |
| 4 | Are the statement and tests aligned in both directions? | 2 | Cases cover ordinary execution, multiple DCP layouts/cache groups, graph replay, and graph metadata; exact internal table width is no longer scored. | None. |
| 5 | Do tests exercise the actual behavior-determining path? | 2 | Production block-table, Triton slot kernel, real model-runner constructor and cache initialization, graph path, and attention metadata run on an H20; only unrelated heavyweight workers, weights, and multiprocess launch are substituted. | None. |
| 6 | Can different correct implementations pass? | 2 | The materially different alternative patch scores 1 after both the representation-specific width check and the partially initialized `GPUModelRunner.__new__` fixture were removed. | None. |
| 7 | Are incorrect implementations rejected for the right reasons? | 2 | Base fails rank-local slots; incomplete eager-only work fails graph metadata, not setup. | None. |
| 8 | Is the Oracle independently validated? | 2 | Oracle passes held-out layouts, position mutation plus graph replay, and the correct-alternative challenge. | None. |
| 9 | Is the grading result trustworthy? | 2 | Full Harbor entrypoint gives 0 to both early-exit controls despite child exit code 0 and gives 1 only after the success token. | None within demonstrated boundary. |
| 10 | Is acceptance reproducible and the handoff clear? | U | Final image identity, executable hashes, build/provenance checks, H20 Harbor results, limitations, and raw-result locations are recorded, but the task declares an A100 runner. | Replay the final matrix on official A100 hardware. |

Gate 1 (statement) and Gate 3 (verification) pass on the final image; Gate 2 remains pending only for the declared A100 runner because local validation used an H20. After the 2026-09-15 constructor-fairness repair, Harbor H20 Base/Oracle produced `0/1`, while direct H20 replay of Base/Oracle/alternative/incomplete/SystemExit/os._exit produced `0/1/1/0/0/0`. Replaying all three saved 1000-turn DeepSeek V4 Flash candidate worktrees produced `0/0/0`: their earlier synthetic-constructor errors disappeared, and each now reaches an intended graph-metadata failure. This confirms the candidates remain incomplete without relying on skipped constructor state.
