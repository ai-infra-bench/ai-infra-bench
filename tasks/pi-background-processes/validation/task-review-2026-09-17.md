# Task review, 2026-09-17: pi-background-processes (0.0.4, harness revision 2)

Review made with `.agents/skills/ai-infra-bench-task-review` (SKILL.md `41a993d17456fe5d`, review-rubric.md `95dc3bd21b3b82b1`, audit_task_artifacts.py `826fa91c261b0819`, agent-harness reference `b8182e7a50f33431`), by the curator session that built and rolled out the task; it is not an independent second opinion. Mode: review (no hardening applied in this pass).

## Snapshot

- Worktree `/Users/bytedance/projects/ai-infra-bench`, branch `agent/pi-background-processes` (task files identical on `agent/pi-agent-trace` at review time), HEAD `f8e309b` before this report.
- Task 0.0.4 (harness revision 2), Base `d981de1229ef899957bbe968bc8dcda02a21f477`, cutoff `2026-09-05T11:54:46Z`, canonical image `sha256:40fe5f96…`, local `713cd7342900`; `[agent].timeout_sec` 36000, agent and verifier `no-network`, 4 CPUs / 8 GiB.

## Disposition

**Retain, needs targeted hardening before final acceptance** (F1 is a demonstrated grading bypass; all other gates pass).

Scored dimensions: 10/10, unverified: 0, sum 17/20. Blocking: F1 (dimension 9). Non-blocking warnings: none for the agent budget (`[agent].timeout_sec` = 36000 s).

| # | Dimension | Score / status | Key evidence or gap | Next action |
|---|---|---|---|---|
| 1 | Is the task realistic and clear? | 2 | A team's request for background processes in pi, told as an issue (0.0.3): symptoms, the ask, the agreed interface, expected behaviour, lifecycle; interfaces exist at Base; no quoted logs; every mechanism hint removed in 0.0.2; the SIGTERM outcome made unmistakable in 0.0.4 after it cost three rollouts. | none |
| 2 | Is correctness independent of the source PR? | 2 | No source PR; statement defines correctness; Oracle plus three non-Oracle passes (`alternative-class-manager-sparse-index`, `alt-grok-0.0.4-vitest-guard`, `alt-grok-0.0.4-clean-pass`). | none |
| 3 | Can the agent solve the task in the environment? | 2 | Same image lineage and audit results as pi-agent-trace (identical Dockerfile bytes, image id `40fe5f96…` / local `713cd7342900`): exact Base, clean, no remotes/tags/reflog/unreachable objects, curator directories absent, agent `no-network`; `/opt/pi-baseline` visible (non-blocking). | none |
| 4 | Are the statement and tests aligned in both directions? | 1 | `validation/behavior-map.md` maps requirements to cases and cases to clauses; two clauses are covered only by the curator-side challenge (relative cwd resolution, paging past the end / kill of a finished process) and documented as such; `SIGINT`, tree navigation and `cleanup.timeoutSec` expiry are documented limitations. Shortfall as in agent-trace: "do not modify pi core" is not verified (F2). Non-blocking. | F2 |
| 5 | Do tests exercise the actual behavior-determining path? | 2 | Real AgentSession, real fixture processes (`emit.mjs`, SIGTERM-ignoring child with a grandchild), real OS process state (`/proc`), separate child pi processes for exit/SIGTERM/durability, heap measurement for the log flood; faux provider only chooses tool calls. Harness revisions of 2026-09-16/17 removed two spill-over artefacts (drain timing, VITEST leak) without changing any case. | none |
| 6 | Can different correct implementations pass? | 2 | Three non-Oracle passes, two of them unmodified real grok-4.6 submissions (one with an environment guard, one without), differing from the Oracle in module structure, log storage and signal handling. | none |
| 7 | Are incorrect implementations rejected for the right reasons? | 2 | Base 0 (`Tool bg_run not found`, built-in `bash` rejects `stalledSec`); 12 negative controls with recorded rejecting layers; two real submissions kept as expected-0 controls (SIGTERM listener never re-raises; listener deferral plus reload `instanceof`); matrix 19/19 locally (`bg-matrix-0.0.4-rev2.log`) and CI x64 green (#92). | none |
| 8 | Is the Oracle independently validated? | 2 | `validation/independent_challenge.py` / `independent_probe.mjs`: four cases absent from the suites (relative cwd + Unicode error pattern, intermittent output stays foreground, paging past the end, `bg_kill` on a finished process); Oracle and both real passes 4/4; `baseline_pin_forgery_check.py` shows the PASS_TO_PASS pins reject rewritten baselines. | none |
| 9 | Is the grading result trustworthy? | 0 | F1 (same `test.sh` shape): runner substitution yields reward 1 on Base (`~/ai-infra-scratch/probe-runner-forge-bg/`). Early-exit and forged-report controls hold at their own boundary. | F1 hardening |
| 10 | Is acceptance reproducible and the handoff clear? | 2 | Strict artifact audit 0/0, `git diff --check` clean, evidence hashes match, Harbor matrix and CI x64 run; README lists validation, rollouts, limitations and remaining publication steps; `publication_state` `staged-smoke-only`. Evidence gap noted in the rollout review: the 2026-09-14/15 attempts are documented without job identities (does not affect acceptance evidence). | publication workflow |

## Gates

- **Gate 1 (statement): pass.** See dimension 1; the interface section is necessarily detailed because the verifier drives named tools, and it is framed as an agreed interface rather than a specification.
- **Gate 2 (environment): pass.** Semantic boundary: `bg_run`/`bash`/`bg_*` tool calls and pi lifecycle events -> candidate process management, log storage and wake routing -> tool results, custom messages in the session, OS process state, files under the session directory (`validation/behavior-map.md`).
- **Gate 3 (verification): blocked by F1.** Coverage, reachability (every case enters through tool calls and pi lifecycle operations on a real session or a real child process), causal wake-timing checks and controls otherwise pass.

## Findings

### F1 (P0, confirmed at the grading-script level): the verifier trusts a test runner the candidate can rewrite

- **Contract requirement:** evaluation integrity (rubric step 10), not a candidate feature. The instruction forbids modifying pi core; nothing forbids or detects edits under `node_modules/`, which `tests/test.sh` excludes from the recorded diff and then executes (`node ../../node_modules/vitest/vitest.mjs run ...`) for all three layers.
- **Reproduction (2026-09-17, task image `713cd7342900`, workspace left at Base, no extension):** replace `node_modules/vitest/vitest.mjs` with a 25-line script that, when asked to run files under `test/__verifier__/`, parses the `it("...")` titles of exactly those files (visible at verify time because `test.sh` copies them into the workspace), writes a JUnit report marking them all passed, and otherwise delegates to the real runner (so PASS_TO_PASS still runs genuinely). `bash /tests/test.sh` then reports contract 15/15 and lifecycle 2/2 (bg: 15/15, 3/3), `check_junit.py` accepts the exact inventory, and `reward.json` is `{"reward":1,...}`. Logs: `~/ai-infra-scratch/probe-runner-forge/` (agent-trace) and `probe-runner-forge-bg/`. Ran through the grading script inside the task image; the Harbor entrypoint adds artifact transfer and reward collection but executes the same script, so full-entrypoint confirmation is expected to match (pending, not yet run).
- **Reachability:** the agent runs as root in this image (no `agent.user`), `node_modules/vitest/vitest.mjs` is writable, and the forger needs no knowledge of hidden case names. The existing `control-forged-junit` covers a candidate writing the report file itself, which the real run overwrites; it does not cover replacing the process that writes it.
- **Attribution:** broken scorer trust boundary (uncovered bypass). Shared by every task in this repository whose verifier executes a workspace-installed runner (18 `tests/test.sh` files), so the decision is repository-level, but for these two tasks it blocks final acceptance until mitigated or explicitly accepted as the benchmark's threat model.
- **Smallest remediation (not applied; needs authorization):** pin, in `tests/` (trusted, outside the image), the SHA-256 of a manifest of `node_modules` computed at image build (`find node_modules -type f | sort | xargs sha256sum | sha256sum`, 2.6 s over 16 796 files / 398 MB in this image) plus the digests of `/usr/local/bin/node`, `python3` and `bash`, and have `test.sh` recompute and compare before running anything; fail the verifier with a readable reason on mismatch. Structural option to evaluate separately: run the agent as the image's existing `node` user (uid 1000) with `node_modules` and the interpreters root-owned, which removes the write path instead of detecting it (needs image chown of the writable paths, a check that the agent can still run pi's tests, matrix and CI reruns). Either change is a verifier/environment change requiring a new matrix and Harbor validation.

### F2 (non-blocking, P2 candidate): the "do not modify pi core" rule is not verified

As for pi-agent-trace: a diff check in `test.sh` restricted to `packages/coding-agent/examples/extensions/background-processes/**`, `packages/coding-agent/test/**` (new files only) and READMEs would score the stated constraint. No recorded submission touched core.

### F3 (informational): environment guards

The `alt-grok-0.0.4-vitest-guard` alternative skips its exit hooks under `VITEST`; harmless in a real pi and now unobservable by the verifier (harness revision 2 keeps runner variables out of the child pi). Recorded so that a future reviewer does not mistake it for special-casing the verifier.


## Evidence actually executed for this review

- `audit_task_artifacts.py tasks/pi-background-processes --strict-evidence`: 4 checks, 0 errors, 0 warnings.
- Image audit as recorded for pi-agent-trace (same image id and Dockerfile bytes).
- Independent challenge: `alt-grok-0.0.4-clean-pass` and `alt-grok-0.0.4-vitest-guard` 4/4 (`~/ai-infra-scratch/bg-challenge-*`); Oracle result recorded in `e2e-evidence.json` (`independent_oracle_challenge`).
- F1 probe: `~/ai-infra-scratch/probe-runner-forge-bg/reward.json` = reward 1 on Base.
- Reused executed evidence: matrix 19/19 (`bg-matrix-0.0.4-rev2.log`), CI x64 on PR #92, rollout review `validation/rollout-review-2026-09-17.md`.

## Next actions

1. Decide on F1 (shared with pi-agent-trace); rerun matrix and CI; rescore dimension 9.
2. Optional F2 check.
3. Image publication before release.
4. Independent reviewer to repeat the scorecard.
