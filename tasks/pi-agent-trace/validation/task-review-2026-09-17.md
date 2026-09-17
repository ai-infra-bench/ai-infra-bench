# Task review, 2026-09-17: pi-agent-trace (0.0.6, verifier revision 2)

Review made with `.agents/skills/ai-infra-bench-task-review` (SKILL.md `41a993d17456fe5d`, review-rubric.md `95dc3bd21b3b82b1`, audit_task_artifacts.py `826fa91c261b0819`, agent-harness reference `b8182e7a50f33431`), by the curator session that built and rolled out the task; it is not an independent second opinion. Mode: review (no hardening applied in this pass).

## Snapshot

- Worktree `/Users/bytedance/projects/ai-infra-bench`, branch `agent/pi-agent-trace`, HEAD `2304dae` at review start (this report and the new validation files are committed on top), tracked tree clean apart from untracked scratch (`debug/`, `span.log`, not part of the task).
- Task 0.0.6, Base `d981de1229ef899957bbe968bc8dcda02a21f477`, cutoff `2026-09-05T11:54:46Z`, canonical image id `sha256:40fe5f96…` (linux/amd64), local image `713cd7342900`; `[agent].timeout_sec` 36000, agent and verifier `no-network`, 4 CPUs / 8 GiB.

## Disposition

**Retain, needs targeted hardening before final acceptance** (F1 is a demonstrated grading bypass; all other gates pass).

Scored dimensions: 10/10, unverified: 0, sum 17/20. Blocking: F1 (dimension 9). Non-blocking warnings: none for the agent budget (`[agent].timeout_sec` = 36000 s).

| # | Dimension | Score / status | Key evidence or gap | Next action |
|---|---|---|---|---|
| 1 | Is the task realistic and clear? | 2 | Constructed developer request (eval harness needs a trace of the agent loop); interfaces used exist at Base (extension events, SessionManager.getBranch, faux provider); no quoted logs or numbers; 0.0.5/0.0.6 state outcomes and an export contract, mechanisms removed; `README.md` records every wording revision. | none |
| 2 | Is correctness independent of the source PR? | 2 | No source PR; the statement defines correctness; the Oracle is one reference (17/17) and three other implementations pass (`alt-grok-run5`, `alt-grok-run8-fixed`, `alt-opus-run1`). | none |
| 3 | Can the agent solve the task in the environment? | 2 | Image audited 2026-09-17: root user, workdir `/workspace/pi` at exactly `d981de12` with a clean tree, 0 remotes/tags/reflog, no packed-refs, 0 unreachable objects, history reachable only up to Base (commit date = cutoff `2026-09-05T11:54:46Z`); npm deps from the repository's own lock at Base (`npm ci`, lock sha pinned); `/tests`, `/solution`, `/validation` absent; agent network `no-network`. `/opt/pi-baseline` (pi's own suite results at Base) is agent-visible: a diagnosis aid for environment failures, not answer material (non-blocking). | none |
| 4 | Are the statement and tests aligned in both directions? | 1 | `validation/behavior-map.md` (written in this review) maps every instruction requirement to cases and every scored assertion to a sentence; verifier-clock windows have 1 ms slack, mixed-clock comparisons are millisecond-granular (revisions of 2026-09-16). Shortfall: the deliverable rule "do not modify pi core" has no coverage beyond PASS_TO_PASS (a core edit that keeps pi's suite green is accepted). Non-blocking; a cheap check is proposed (F2). | F2 |
| 5 | Do tests exercise the actual behavior-determining path? | 2 | Real AgentSession, extension runner, tool execution, steering/follow-up delivery, compaction (manual, threshold, overflow retry), file-backed SessionManager, reload, separate child pi processes (lifecycle, sub-agent). Substituted: the model (first-party faux provider, scripted) and tools (`echo`, `boom`, `spawn_child`), neither of which determines span structure, persistence order, timing class or lifecycle. Causal live-update check (file read while a 1.5 s tool runs). | none |
| 6 | Can different correct implementations pass? | 2 | Three non-Oracle implementations pass every layer: two unmodified real submissions (grok 0.0.4, opus 0.0.6) and one real submission with a 54-line curator fix; they differ in write timing (immediate vs turn-end buffering), clock construction and entry resolution. Exact attribute maps replaced by listed-keys matching after run 11. | none |
| 7 | Are incorrect implementations rejected for the right reasons? | 2 | Base 0 (no trace file, not a harness error); 27 negative controls each rejected by the layer named in `validation/controls-plan.md`; three real 0.0.1/0.0.3 submissions rejected by exactly the cases their revision added; matrix 31/31 locally (`at-matrix-11.log`) and CI x64 green (#94). | none |
| 8 | Is the Oracle independently validated? | 2 | New in this review: `validation/at.independent.test.ts` + `independent_challenge.py`, two scenarios the suite never composes (failing first tool + manual compaction + parallel batch with one failure; PI_AGENT_TRACE_FILE + reload + wakeup in one session), expectations derived from the instruction. Oracle 2/2, the three alternatives 2/2, three negative controls and the 0.0.1 submission rejected. Shared invariants (`traceProblems`, `liveProblems`) are reused; no scored case is copied. | none |
| 9 | Is the grading result trustworthy? | 0 | F1: a candidate-writable test runner yields reward 1 with Base code through `tests/test.sh` (reproduced). Existing safeguards (exact JUnit inventory, forged-report control, early-exit control, baseline pins) do not cover runner substitution. | F1 hardening |
| 10 | Is acceptance reproducible and the handoff clear? | 2 | `audit_task_artifacts.py --strict-evidence` 0 errors 0 warnings, `git diff --check` clean, evidence hashes match the executable artifacts, formal Harbor path run locally (matrix) and in CI (x64); README records revisions, controls, rollouts and limitations; `publication_state` is `staged-smoke-only` (image publication is a release step). | publication workflow |

## Gates

- **Gate 1 (statement): pass.** A plausible request from a team that runs pi as its harness; every interface named exists at Base; no historical claims; 8.6 KB of outcome requirements plus an export contract. The 2026-09-16 rollouts showed each defect maps to an explicit sentence.
- **Gate 2 (environment): pass.** See dimension 3. Semantic boundary: pi agent-loop events -> candidate span bookkeeping and file writes -> OTLP/JSON lines checked against the session branch and the verifier's event recorder (`validation/behavior-map.md`).
- **Gate 3 (verification): blocked by F1** (scorer trust). Coverage, fixture reachability (every case enters through `AgentSession.prompt`, `compact`, `reload`, `abort`, `dispose`, extension `sendMessage` and real child processes; no directly constructed internal state), timing rules and controls otherwise pass.

## Findings

### F1 (P0, confirmed at the grading-script level): the verifier trusts a test runner the candidate can rewrite

- **Contract requirement:** evaluation integrity (rubric step 10), not a candidate feature. The instruction forbids modifying pi core; nothing forbids or detects edits under `node_modules/`, which `tests/test.sh` excludes from the recorded diff and then executes (`node ../../node_modules/vitest/vitest.mjs run ...`) for all three layers.
- **Reproduction (2026-09-17, task image `713cd7342900`, workspace left at Base, no extension):** replace `node_modules/vitest/vitest.mjs` with a 25-line script that, when asked to run files under `test/__verifier__/`, parses the `it("...")` titles of exactly those files (visible at verify time because `test.sh` copies them into the workspace), writes a JUnit report marking them all passed, and otherwise delegates to the real runner (so PASS_TO_PASS still runs genuinely). `bash /tests/test.sh` then reports contract 15/15 and lifecycle 2/2 (bg: 15/15, 3/3), `check_junit.py` accepts the exact inventory, and `reward.json` is `{"reward":1,...}`. Logs: `~/ai-infra-scratch/probe-runner-forge/` (agent-trace) and `probe-runner-forge-bg/`. Ran through the grading script inside the task image; the Harbor entrypoint adds artifact transfer and reward collection but executes the same script, so full-entrypoint confirmation is expected to match (pending, not yet run).
- **Reachability:** the agent runs as root in this image (no `agent.user`), `node_modules/vitest/vitest.mjs` is writable, and the forger needs no knowledge of hidden case names. The existing `control-forged-junit` covers a candidate writing the report file itself, which the real run overwrites; it does not cover replacing the process that writes it.
- **Attribution:** broken scorer trust boundary (uncovered bypass). Shared by every task in this repository whose verifier executes a workspace-installed runner (18 `tests/test.sh` files), so the decision is repository-level, but for these two tasks it blocks final acceptance until mitigated or explicitly accepted as the benchmark's threat model.
- **Smallest remediation (not applied; needs authorization):** pin, in `tests/` (trusted, outside the image), the SHA-256 of a manifest of `node_modules` computed at image build (`find node_modules -type f | sort | xargs sha256sum | sha256sum`, 2.6 s over 16 796 files / 398 MB in this image) plus the digests of `/usr/local/bin/node`, `python3` and `bash`, and have `test.sh` recompute and compare before running anything; fail the verifier with a readable reason on mismatch. Structural option to evaluate separately: run the agent as the image's existing `node` user (uid 1000) with `node_modules` and the interpreters root-owned, which removes the write path instead of detecting it (needs image chown of the writable paths, a check that the agent can still run pi's tests, matrix and CI reruns). Either change is a verifier/environment change requiring a new matrix and Harbor validation.

### F2 (non-blocking, P2 candidate): the "do not modify pi core" rule is not verified

The instruction requires the extension to live under `examples/extensions/agent-trace/` and to leave pi core unchanged; the verifier only enforces that existing test files are untouched and pi's suite still passes. A one-line check in `test.sh` (fail if the recorded diff touches `packages/*/src/**`) would make the constraint scored; it is contract-backed and would not affect any recorded submission (none touched core). Needs a matrix rerun if adopted.

### F3 (informational): early-exit and report-forgery controls hold at the boundary they test

`control-forged-junit` and `control-process-exit-zero-after-registration` are rejected in the matrix (reward 0) and reach their intended boundary (the forged file is overwritten by the real run; the early `process.exit(0)` leaves the inventory incomplete). They do not cover F1.


## Evidence actually executed for this review

- `python3.12 .agents/skills/ai-infra-bench-task-review/scripts/audit_task_artifacts.py tasks/pi-agent-trace --strict-evidence`: 4 checks, 0 errors, 0 warnings.
- Image audit inside `ai-infra-bench/pi-agent-trace:local` (id `713cd7342900`, arm64 local build of the canonical Dockerfile; amd64 canonical `40fe5f960138`): HEAD `d981de12`, clean, isolation checks as in dimension 3.
- Independent challenge runs: oracle, `alt-opus-run1`, `alt-grok-run8-fixed`, `alt-grok-run5` all 2/2; `control-tool-error-status-ok`, `control-compaction-under-last-run`, `control-trace-id-per-process`, `alt-grok-run1` rejected (logs `~/ai-infra-scratch/at-challenge-*`).
- F1 probe: `~/ai-infra-scratch/probe-runner-forge/reward.json` = reward 1 on Base.
- Prior executed evidence reused (not rerun here): local matrix 31/31 (`~/ai-infra-scratch/at-matrix-11.log`), CI x64 validation on PR #94, rollout review `validation/rollout-review-2026-09-17.md`.

## Next actions

1. Decide on F1: adopt the pinned-manifest check in `test.sh` (both pi tasks, and consider the repository-wide pattern) or the non-root agent user; rerun the matrix and CI; then rescore dimension 9.
2. Optional F2 check, same rerun.
3. Image publication through `publish-task-images.yml` before release.
4. An independent reviewer should repeat the scorecard; this one was produced by the task's own curator.
