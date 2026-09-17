# pi-plan-mode

**Status: locally validated; image publication pending.** Validated through the
Harbor entrypoint on a retained linux/amd64 image: Base 0, Oracle 1, one correct
alternative 1, one public-output variant 1, and ten negative controls 0. Recorded results are in
[`validation/e2e-evidence.json`](validation/e2e-evidence.json).

## What the agent does

Enhances the existing Plan Mode example extension in
[pi](https://github.com/earendil-works/pi) at a pinned commit. Approval must identify
the exact session, plan, and revision the user reviewed. The task covers explicit
plan submission, interactive and RPC controls, stale-approval rejection, exact
restoration of the prior tool selection, and normal session resume without
repeating execution. The benchmark evaluates the coding agent's patch to pi.
See [`instruction.md`](instruction.md) for the authoritative contract.

Changes are limited to the Plan Mode extension and its README, the existing
`plan-mode-extension.test.ts`, and new coding-agent tests. Core, dependencies,
build configuration, unrelated extensions, and unrelated tests remain unchanged.
Repeating `/plan` no longer restores writing, and arbitrary custom tools are not
enabled during planning.

## Environment

- Base: `earendil-works/pi` at `d981de1229ef899957bbe968bc8dcda02a21f477`
  (v0.85.1); dependency cutoff `2026-09-05T11:54:46Z`.
- Pinned Node 22.19.0 bookworm-slim, `npm ci` with the Base's original lockfile,
  and a prebuilt pi workspace. `fd` 10.2.0, ripgrep, and Python are installed
  so runtime tools and verifier helpers work offline.
- The Dockerfile is generated from `environment/build/Dockerfile.template`.
  The builder uses an empty context and records the image identity in
  `environment/image-manifest.json`; `task.toml` pins that identity.
- CPU only: 4 CPUs, 8 GiB RAM, 20 GiB storage; agent timeout 10 hours and
  verifier timeout 1 hour. The agent runs as `pi-agent` in `/workspace/pi`.
- The environment has no network by default. Verification uses pi's first-party
  faux provider, with provider credentials unset and `PI_OFFLINE=1`; it makes no
  real model requests. Building the image requires access to the pinned source
  and packages.
- Task tests, reference solutions, and validation artifacts are excluded from
  the image. The image records the original coding-agent test baseline under
  `/opt/pi-baseline/`.

The image permits editing only the allowed extension and tests, with writable
scratch and cache directories for normal test commands. Dependencies, Git
metadata, and core configuration are protected. During verification, submitted
sources are frozen, candidate caches are discarded, and candidate test workers
run as UID 65534, separate from the root coordinator and its reports.

## Verifier

`tests/test.sh` runs the following layers. Reward is 1 only if every required
layer passes; a successful candidate process exit alone is insufficient.

| Layer | File | What it observes |
| --- | --- | --- |
| Scope | `tests/check_scope.py` | Only the allowed extension and test files changed; core, dependencies, configuration, and unrelated files match the frozen Base. |
| PASS_TO_PASS | `tests/check_pass_to_pass.py`, `tests/baseline-pins.json` | The pinned Base inventory and the current original-test results match: 2,154 required cases, unchanged skips, and no unaccepted regressions. The four intentionally replaced legacy Plan Mode tests are excluded; Plan Mode utilities remain protected. |
| Contract (18 cases) | `tests/plan.contract.test.ts` | Real extension loading, `AgentSession` input and tool dispatch, structured drafts, revision-bound approval, source restrictions, exact tool restoration, one execution request, busy-state rejection, interactive review actions and their actual execution context, and read-only progress display. Includes one grading-permission precondition. |
| Lifecycle (4 cases) | `tests/plan.lifecycle.test.ts`, `tests/fixtures/plan_child.mjs` | Separate pi processes and real file-backed sessions: planning resumes restricted; approved plans retain their snapshot and tools without replay; foreign state is ignored; persisted normal state takes precedence over `--plan`. |
| Integrity | `tests/check_junit.py`, `tests/test_integrity.py` | Exact completed contract/lifecycle inventories with no failures, errors, or skips; malformed, missing, and early-exit reports cannot produce a passing reward. |

Verifier scenarios are copied into `packages/coding-agent/test/__plan_verifier__/`
only at verification time. Model responses and UI choices are scripted; the
extension, dispatcher, input-source handling, persistence, and scheduling run
through pi's real public APIs. Displayed custom messages and component widgets
use pi's actual renderers with an in-memory terminal. The behavior-to-test mapping is in
[`validation/behavior-map.md`](validation/behavior-map.md).

One unrelated AuthStorage assertion was reproduced on untouched Base. It remains
in the required inventory and raw reports, and is accepted only when every
reported attempt matches its exact pinned error. Other regressions or changed
skips fail. See
[`validation/baseline-environment.md`](validation/baseline-environment.md).

## Validation (2026-09-17, v0.0.3)

All 14 cases completed through Harbor 0.23.0 with the retained linux/amd64 image,
with zero errored trials and the expected reward in every case.

| Case | Agent / implementation | Expected reward | Result |
| --- | --- | --- | --- |
| `base` | `nop`, unchanged Base | 0 | 0; scope and PASS_TO_PASS pass; 17 behavior checks and 4 lifecycle checks fail because the requested behavior is absent. |
| `oracle` | `oracle`, reference patch | 1 | 1; all layers pass, including 18/18 contract and 4/4 lifecycle cases. |
| `alternative-event-journal` | `oracle`, independent event-journal patch applied to Base | 1 | 1; all layers pass, including 18/18 contract and 4/4 lifecycle cases. |
| `minimal-public-state` | `oracle`, reference-derived public-output variant | 1 | 1; all layers pass without `approvedRevision`, with extra diagnostics, details-only submission output and free-text rejection reasons. |
| `accept-stale-revision` | `oracle`, Base-applicable negative-control patch | 0 | 0; C06, C15 detect acceptance of stale approvals. |
| `accept-extension-control` | `oracle`, Base-applicable negative-control patch | 0 | 0; C07 detects extension-origin controls. |
| `replay-duplicate-approval` | `oracle`, Base-applicable negative-control patch | 0 | 0; C10, C16 detect duplicate execution. |
| `allow-custom-planning-tools` | `oracle`, Base-applicable negative-control patch | 0 | 0; C02, C09, L01 detect incorrectly enabled tools. |
| `replay-approved-resume` | `oracle`, Base-applicable negative-control patch | 0 | 0; L02 detects execution replay after resume. |
| `resume-original-toolset` | `oracle`, Base-applicable negative-control patch | 0 | 0; L01 detects unrestricted tools after planning resume. |
| `drop-approved-request-context` | `oracle`, Base-applicable negative-control patch | 0 | 0; C10, C16 detect the approved snapshot missing from actual model input. |
| `early-exit-zero` | `oracle`, Base-applicable negative-control patch | 0 | 0; C01–C17 and L01–L04 reject incomplete checks despite a zero process exit. |
| `drop-done-progress` | `oracle`, Base-applicable negative-control patch | 0 | 0; C12 detects a progress display that does not advance. |
| `drop-ui-approved-request-context` | `oracle`, Base-applicable negative-control patch | 0 | 0; C16 detects omitted model context only on UI approval; RPC behavior remains correct. |

All 14 author cases passed the full 2,154-case regression gate with 50 original
skips and completed through Harbor 0.23.0. All six integrity self-tests passed.
The unchanged exact AuthStorage exception remains narrowly accepted and is
reported per run in the evidence.

The v0.0.3 revision corrects UI mode, normal shutdown, asynchronous C15 review
handling, legal C17 Stay/Refine inputs and structured state observation. It keeps
the original behavior inventory, scoring policy and CI control patches. See
[`validation/verifier-v0.0.3.md`](validation/verifier-v0.0.3.md) for the contract
basis, full fresh matrix, frozen execution hashes and limitations.

Three complete saved agent answers were also regraded through Harbor without
new model calls: Astra xhigh 1, Astra medium 1, and Sol xhigh 0 (C04/L04).
Their historical v0.0.2 rewards remain 0. Results are in
[`validation/saved-answer-rechecks-v0.0.3.json`](validation/saved-answer-rechecks-v0.0.3.json).
Earlier author and candidate evidence remains explicitly historical in
[`validation/author-results.md`](validation/author-results.md),
[`validation/e2e-evidence-v0.0.2.json`](validation/e2e-evidence-v0.0.2.json), and
`validation/candidate-rechecks.json`.

## Layout

```text
pi-plan-mode/
├── instruction.md                       # Agent-facing behavior contract
├── task.toml                            # Frozen target, resources, and budgets
├── environment/
│   ├── Dockerfile                       # Generated Pi/Node environment
│   ├── image-manifest.json              # Image identity and build metadata
│   ├── build/
│   │   ├── Dockerfile.template          # Baseline and task permissions
│   │   ├── generate.py                  # Render or check the Dockerfile
│   │   └── build.py                     # Empty-context image build
│   └── lock/{package-lock.json,manifest.json}
├── tests/                               # Verifier scenarios and scoring
├── solution/                            # Reference patch and solve.sh
└── validation/                          # Correct alternative, controls, evidence
    ├── ci-cases.json
    ├── alternative-event-journal.patch
    ├── minimal-public-state.patch
    ├── behavior-map.md
    ├── author-results.md
    ├── e2e-evidence.json
    └── run_author_matrix.py
```

## Building and running

Use Python 3.11 or newer, Docker with Buildx, and Harbor. Run these commands from
the benchmark repository root:

```bash
python3 templates/pi-harbor-node/lock.py tasks/pi-plan-mode
python3 tasks/pi-plan-mode/environment/build/generate.py
python3 tasks/pi-plan-mode/environment/build/generate.py --check
python3 tasks/pi-plan-mode/environment/build/build.py --platform linux/amd64
```

Use the task's own generator and builder to preserve its editing permissions
and cache setup. The builder accepts `--builder`, `--network`, repeatable
`--allow`, and repeatable `--build-arg`. The manifest records option names with
host-specific values omitted; build options do not enable verifier networking.

To check the task and run Oracle against an existing image:

```bash
python3 .github/scripts/task_ci.py validate pi-plan-mode
python3 .github/scripts/task_ci.py image-check --task pi-plan-mode \
  --image ai-infra-bench/pi-plan-mode:base-d981de1229ef
python3 .github/scripts/task_ci.py prepare-case --task pi-plan-mode \
  --image ai-infra-bench/pi-plan-mode:base-d981de1229ef \
  --case oracle --output ./harbor-cases/pi-plan-mode-oracle
harbor run --path ./harbor-cases/pi-plan-mode-oracle --agent oracle --env docker \
  --jobs-dir ./harbor-jobs --job-name pi-plan-mode-oracle --n-concurrent 1
python3 .github/scripts/task_ci.py check-result \
  --result ./harbor-jobs/pi-plan-mode-oracle/result.json --expected-reward 1
```

`prepare-case` injects the selected image into a separate task copy, avoiding an
unintentional rebuild. Use `--case base` with agent `nop` to verify the expected
reward 0. A coding-agent trial must also start from a fresh `--case base` copy;
keep reference solutions and validation artifacts hidden during solving, and
configure any required model endpoint access only for the agent phase.

The full validation matrix can be run with:

```bash
python3 tasks/pi-plan-mode/validation/run_author_matrix.py \
  --image ai-infra-bench/pi-plan-mode:base-d981de1229ef \
  --output ./harbor-validation/pi-plan-mode \
  --workers 3
```

Use a new output directory for each run. Add `--cases base oracle` to run only
the two primary checks. `--harbor` can select a Harbor executable or launcher.

## Evaluation limits and remaining work

Existing Plan Mode code is public; this task tests a stronger approval contract
and does not claim contamination-free evaluation. See
[`validation/upstream-history.md`](validation/upstream-history.md). Crash
recovery, shutdown during active execution, fork/tree navigation, extension
reload, and arbitrary shell read-only enforcement are outside the contract.
The verifier protects its reports and toolchain from worker writes; it is not a
universal defense against arbitrary assertion manipulation inside a test worker.

Public image delivery remains pending. The repository publication workflow must
validate the image it actually publishes and retain a pullable immutable image
reference. OS repositories and the Dockerfile frontend are not snapshot-pinned,
so a later rebuild is not guaranteed to produce identical bytes.

Repeated independent coding-agent trials can further calibrate difficulty and
success rates. Construction checks and individual rollouts do not establish a
reliable ranking; adding more trials is separate from task acceptance.
