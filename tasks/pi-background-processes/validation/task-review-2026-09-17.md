# Task review, 2026-09-17: pi-background-processes (0.0.4, harness revision 2)

Review made with `.agents/skills/ai-infra-bench-task-review` (SKILL.md `41a993d17456fe5d`, review-rubric.md `95dc3bd21b3b82b1`, audit_task_artifacts.py `826fa91c261b0819`, agent-harness reference `b8182e7a50f33431`), by the curator session that built and rolled out the task; it is not an independent second opinion. Mode: review (no hardening applied in this pass).

## Snapshot

- Worktree `/Users/bytedance/projects/ai-infra-bench`, branch `agent/pi-background-processes` (task files identical on `agent/pi-agent-trace` at review time), HEAD `f8e309b` before this report.
- Task 0.0.4 (harness revision 2), Base `d981de1229ef899957bbe968bc8dcda02a21f477`, cutoff `2026-09-05T11:54:46Z`, canonical image `sha256:40fe5f96…`, local `713cd7342900`; `[agent].timeout_sec` 36000, agent and verifier `no-network`, 4 CPUs / 8 GiB.

## Disposition

**Retain; F1 hardened on 2026-09-17 (harness revision 3) and revalidated** (initial disposition: needs targeted hardening; see the update below).

Scored dimensions: 10/10, unverified: 0, sum 19/20 after the update (17/20 at the initial review). Blocking: none open (F1 closed 2026-09-17; F3, the verifier-phase counterpart, found and closed 2026-09-18 in harness revision 4; F2 remains non-blocking). Non-blocking warnings: none for the agent budget (`[agent].timeout_sec` = 36000 s).

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
| 9 | Is the grading result trustworthy? | 2 (was 0; F1+F3) | F1 (agent phase) and F3 (verifier phase) closed: candidate code runs as the unprivileged `node` user in **both** the agent phase (rev 3) and the verifier's suites (rev 4, `su -p node` in `test.sh`), with the runner, interpreter, baseline and reward file root-owned; controls `control-toolchain-config-injected` and `control-verifier-runner-escape` (both expected 0) rejected; reward written only by root; node processes reaped between steps. Residual: a suite can still tamper with its own report in-process (bounded; see the 2026-09-18 update). Matrices all-match on the rev-4 image. | none (CI on the rev-4 image) |
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

## Update, 2026-09-17 (harness revision 3)

F1 hardening applied with authorization and revalidated: `task.toml` `[agent].user = "node"` (Harbor-native); the rendered Dockerfile leaves the checkout node-owned and `node_modules`, `node`, `python3`, `bash` root-owned and read-only for the agent, with node-owned `node_modules/.vite-temp` and `.vite` per package and `git config --system safe.directory`; `tests/test.sh` rejects submissions that changed pi source or the build/test toolchain (`scope_exit_code`, `scope.log`) and removes vite's transient bundles; `check_pass_to_pass.py` tolerates the pinned environmental failures in the candidate run (pi's timing-dependent `AuthStorage` case failed for root in the rebuilt image after passing at build time). New control `control-toolchain-config-injected` (expected 0). Probes in the rebuilt image: as `node`, replacing `node_modules/vitest/vitest.mjs` or `/usr/local/bin/node` fails with EACCES; the original F1 forgery cannot be installed; the injected-config control is rejected with the reason logged; Oracle reward 1. Matrices on the rebuilt image: pi-background-processes 20/20 (`~/ai-infra-scratch/bg-matrix-r3.log`). Dimension 9 rescored 2. Remaining: CI on the rebuilt image, canonical amd64 image and manifest, and the two authorized grok-4.6 rollouts on this revision (recorded in the evidence when done).

## Update, 2026-09-18 (harness revision 4): verifier runs candidate code unprivileged

**F3 (P0, confirmed, closed in this update): the verifier executed candidate code as root.** The 2026-09-17 update rescored dimension 9 to 2 on the strength of the *agent-phase* runner-substitution defence alone. Re-review on 2026-09-18 found the same class of bypass still open in the *verifier* phase: `tests/test.sh` ran as root and executed candidate code -- the candidate-added test file inside PASS_TO_PASS, and the candidate extension imported by the contract suite -- so candidate code could overwrite the root-owned `node_modules/vitest/vitest.mjs` during verification and have the later suites run a forged runner. Reproduced on both rebuilt revision-3 images: Base with no real solution plus one added test file reached reward 1 through the real `test.sh` (probe and reward files under `~/ai-infra-scratch/probe-verify-forge/`).

**Fix (authorized).** `tests/test.sh` now runs every suite that executes candidate code (PASS_TO_PASS, contract, lifecycle) as the unprivileged `node` user via `su -p`; each report is produced into a node-owned scratch dir and copied up by root; the reward file is written only by root; `node` processes are reaped between steps; and the snapshot uses a throwaway git index so the real node-owned `.git/index` is never rewritten by root. Because the PASS_TO_PASS baseline must be recorded under the candidate's run conditions, the image now records the baseline as `node` too (the chown-to-node block moved before the baseline `RUN`). New control `control-verifier-runner-escape` (expected 0): the added test's write to the root-owned runner fails EACCES, the case fails in PASS_TO_PASS, reward 0.

**Baseline change.** As `node` the baseline is 2158 tests / 0 failures / 50 skipped: the permission-sensitive cases that failed only because root ignores file modes now pass. `baseline-pins.json` validates unchanged -- the case-name and skipped-set digests are uid-independent, and the tolerated (`allowed_failures`) set is checked as a superset, so its entries may stay even though they now pass on Base.

**Re-validation on the revision-4 image** (arm64 local `sha256:c0b17fef…`; amd64 canonical in `environment/image-manifest.json`): Oracle reward 1; the forgery probe and the new control reward 0 with the readable failed case `test/zz-verifier-runner-escape.test.ts`; the real revision-3 grok submission replays unchanged (bg `…005921` reward 1); full matrix pi-background-processes 21/21 (`~/ai-infra-scratch/f3-bg-matrix.log`). Dimension 9 stays 2, now resting on both the agent-phase and verifier-phase defences.

**Known limitation (dimension 9).** A candidate can still, in principle, tamper with the report of the single suite it runs inside, from within that same `node` process (for example an exit hook that rewrites its own `--outputFile`). That is candidate-side cheating for the hack screen, not a runner or scorer substitution: it is bounded to that suite's own report, while the runner, interpreter, baseline and reward file are all outside the candidate's reach. Closing it fully would require capturing each suite's result through a channel the suite process cannot write, which revision 4 does not attempt.
