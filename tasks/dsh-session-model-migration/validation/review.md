Current seven-task hardening evidence: [dsh-session-model-migration](seven-hardening-review.md). Older results below apply only to their recorded snapshots.

# Task review: version 0.0.2

> Statement revision, 2026-09-11: `instruction.md` has been shortened and reorganized for joint editorial review. See [the revision record](statement-revision.md). The existing execution evidence and pass@4 results refer to the prior statement; no new model run or full task acceptance is claimed for this draft.

> Superseded approval: the post-pass@4 review found three open P1 issues (error-text matching, whole-payload ID substring matching, and empty-session explicit output-cap persistence in both reference implementations). Retain the task for hardening; do not treat the prior approval below as the current release verdict. See [the post-pass@4 review](../../../artifacts/dsh-migration-post-pass4-review-20260910/README.md). The historical execution results below remain unchanged.

Retain this task. The approved hardening is complete: all three review gates pass and the five demonstrated findings below are closed. The task remains an uncommitted development candidate on `main`; no commit, PR, registry publication, or new solver-model run was made. This is a primary-agent review, not a second-agent review.

## Gate 1: scenario

Checked session-local model migration, destination capacity admission, durable reopening, and the declared plaintext Responses gateway are plausible operations at the existing Session Controller and pi-ai interfaces. Upstream discussions #1780 and #1410 motivate this constructed scenario; they are not represented as reproduced incidents. The agent-facing instruction is unchanged. The gateway representation is an explicit local compatibility contract, not a claim about every public OpenAI endpoint.

## Gate 2: environment and cutoff

Semantic boundary: checked `selectModel` input → agent quiescence and revision checks, destination capability resolution, real token-meter admission, durable selection → saved-event reopening → real pi-ai HTTP serialization → tool execution and the next request containing its result.

Loader composition, runtime, session projections, token meter, protocol serialization, and tools run for real. Only catalog answers and model-generated HTTP streams are deterministic substitutes; they preserve ordering, call cardinality, terminal events, and continuation. Reopening round-trips JSON events into a new agent, and tools write real files. A strong solver can reconstruct this path from the normal Base source and dependencies.

Base `4e84901e6471b79ec0338099867ebb4606d12bb5` and cutoff `2026-09-01T15:37:26Z` remain unchanged. The agent image `sha256:e87af67674c9b180ee88328bffd4b4279c1324c0567ac86be943f951287a2b0a` is byte-identical to the previously audited image. Its source/history isolation and dependency provenance remain recorded in `environment/` and `history/v001-task.tar.gz`. The new verifier image `sha256:51c401e6a3a4971729df3c1a6ecafd68538ea90e0ac1787e46001d1a19b366c6` has the same clean Base and locked runtime plus curator-only tests. No task tests, solution, controls, or new diagnosis aids enter the agent image. Both phases use 4 CPUs, 8 GiB memory, 20 GiB storage, no external network, and the unchanged 36,000-second agent budget.

## Gate 3: behavior and result integrity

| Contract | Scored coverage |
|---|---|
| Work survives migration and reopening | Real source tool work, JSON event reopening, new destination tool call, and its result in the following request |
| Rejection is atomic and recoverable | Insufficient capacity leaves events/defaults unchanged; the original route still generates |
| Admission uses destination estimates | Complete retained input, latest system/tools, exact-fit and over-limit cases, unknown capacity, already-selected route |
| Output allowance ownership | Explicit allowance versus adapter default, explicit allowance on an empty session, and persistence through reopening |
| Quiescence and session locality | Queued/running work, stale asynchronous checks, sibling/default isolation, and permissive legacy selection |
| Reasoning and replay | Provider/model changes, ordered plaintext, foreign state removal, native same-route fidelity, default-off and missing-reasoning behavior |
| Tool call cardinality | Parallel calls and results, including distinct IDs whose pipe prefixes coincide; generated ID spelling is not prescribed |
| Configuration | Reject incompatible protocols while accepting a valid protocol inherited from the installed catalog |

The 22 expected names are frozen in `tests/expected-tests.json`. The reference projects replay before serialization; the correct alternative uses a final payload hook and two-pass call mapping. Both pass 22/22. The separate local review probe performs a failed second migration after a successful pending selection and then reopens; both implementations pass 1/1. It is additional lifecycle evidence, not a scored Harbor case.

Harbor now transfers only a source patch to a separate clean verifier. The grader rejects infrastructure-path and link replacements and never copies agent-side dependencies or Git state. The trusted runner and result directory are root-owned; candidate modules execute in UID/GID 65534 workers with `no_new_privs`. The parent requires successful child completion, the exact assertion collection, all passes, and no pending/skipped tests. A root interpreter alone was insufficient in version 0.0.1 because the runner itself was candidate-writable.

## Closed findings

| Finding | Counterexample and repair | Final evidence |
|---|---|---|
| R1 / P0: replaceable test runner | Base source previously earned 1 after agent-side Vitest replacement. Separate clean verifier and unprivileged workers prevent that demonstrated route and direct report writes. | Forged runner: real 8/22, reward 0; report write denied with EACCES, reward 0 |
| R2 / P1: output cap lost on reopen | Explicit 177 became adapter default 128. Reference and alternative now recover persisted caller-owned allowance. | New scored reopen regression passes; exact old model and old reference fail |
| R3 / P1: empty-session budget | Explicit 177 was admitted into capacity 32. Admission now uses caller options before any request header exists. | New scored empty-session regression passes; old reference fails |
| R4 / P1: tool-ID collision | `shared|opaque_a` and `shared|opaque_b` collapsed to one ID in the model submission. | New scored cardinality/pairing regression rejects that unchanged submission; both correct implementations pass |
| R5 / P1: inherited protocol rejected | A valid installed Responses model omitted an explicit `api`. Configuration now validates resolved catalog protocols. | New scored inherited-protocol regression passes; old reference fails |

The original review, reproducer evidence, and pre-hardening task are retained under `validation/history/`. No model submission was repaired or substituted to obtain these outcomes.

## Final runs

| Candidate | Completed passes | Docker reward | Harbor reward |
|---|---:|---:|---:|
| base | 8/22 | 0 | 0 |
| oracle | 22/22 | 1 | 1 |
| early-exit | incomplete | 0 | 0 |
| no-budget | 18/22 | 0 | 0 |
| no-revision-check | 21/22 | 0 | 0 |
| global-default | 21/22 | 0 | 0 |
| no-reasoning-transfer | 19/22 | 0 | 0 |
| alternative-payload-projection | 22/22 | 1 | 1 |
| old-reference | 19/22 | 0 | 0 |
| model-original | 20/22 | 0 | 0 |
| forged-report | incomplete | 0 | 0 |
| forged-runner | 8/22 | Harbor-only | 0 |

All 13 Docker runs and 13 full Harbor trials have their expected rewards. Docker includes repeated clean Base and Oracle runs; Harbor covers 12 candidate classes and a final Oracle repeat. There are zero Harbor exceptions. Native early exit reaches `selectModel` in four workers; the runner exits 1 and reward remains 0. Direct report forgery is denied in four workers before native exit. The forged-runner Harbor trial confirms its agent marker and transfers an empty source patch, so the clean verifier executes real Base tests.

Final Oracle job `6ff30982-794c-4172-9380-501e2f6a9c4e`, trial `b0d4bba7-ac94-4d59-8a39-b8d00dd76ce5` (`oracle-final__Lu2PPCZ`), input checksum `4d0ea0c2a60ab1e0f6e7a564d3ffc8ff73fcba0d7063e75895a69b07bfbc3d06`: reward 1, 22/22, no pending tests or exceptions. Focused source regressions pass 113/113 in six files, including all 14 legacy selection tests; affected TypeScript projects compile.

The original GPT-5.6 Sol high run retains its historical 18/18 and reward 1 under version 0.0.1. Regrading its exact patch `c81fd00ef53c1c07923bd2a320889b3e8a0a9afab97e970e1a17173507cc2486` under 0.0.2 produces 20/22 and reward 0: explicit cap persistence and tool-ID cardinality fail. Original run artifacts are unchanged; no fresh solver-model call occurred during hardening.

## Evidence and limits

[Machine-readable evidence](e2e-evidence.json) records every executable hash, image identity, command, result, and final Harbor identifier. [Raw evidence](evidence.tar.gz) includes image/build, Docker, and Harbor logs; only `docker-final-results.json` and `harbor-final-results.json` certify the final candidate. Earlier preflight failures in the archive are superseded. [Source checks](source-checks.json) and the independent probe are separate local validation.

Harbor task copies inject the two retained local image tags. Their input checksums precede evidence/documentation writes; final executable hashes match all 30 uploaded executable artifacts. Documentation and evidence written afterward do not change the tested executables. Image IDs are Docker identities, not published registry digests.

The security claim is limited to the exercised runner-replacement, direct-report-forgery, and premature-exit controls; this is not a proof against every possible hostile runtime or IPC attack. Admission remains an estimate at selection time, not exact provider tokenization or guaranteed future capacity. No full upstream lint/build/doc-sync suite or live external gateway conformance is claimed.
