# pi-plan-mode

**Status: development.** Validated through the Harbor entrypoint on a retained
linux/amd64 image: Base 0, Oracle 1, one correct alternative 1, and eight negative
controls 0. The image is not yet published. Recorded results are in
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
| Contract (18 cases) | `tests/plan.contract.test.ts` | Real extension loading, `AgentSession` input and tool dispatch, structured drafts, revision-bound approval, source restrictions, exact tool restoration, one execution request, busy-state rejection, and interactive review actions. Includes one grading-permission precondition. |
| Lifecycle (4 cases) | `tests/plan.lifecycle.test.ts`, `tests/fixtures/plan_child.mjs` | Separate pi processes and real file-backed sessions: planning resumes restricted; approved plans retain their snapshot and tools without replay; foreign state is ignored; persisted normal state takes precedence over `--plan`. |
| Integrity | `tests/check_junit.py`, `tests/test_integrity.py` | Exact completed contract/lifecycle inventories with no failures, errors, or skips; malformed, missing, and early-exit reports cannot produce a passing reward. |

Verifier scenarios are copied into `packages/coding-agent/test/__plan_verifier__/`
only at verification time. Model responses and UI choices are scripted; the
extension, dispatcher, input-source handling, persistence, and scheduling run
through pi's real public APIs. The behavior-to-test mapping is in
[`validation/behavior-map.md`](validation/behavior-map.md).

One unrelated AuthStorage assertion was reproduced on untouched Base. It remains
in the required inventory and raw reports, and is accepted only when every
reported attempt matches its exact pinned error. Other regressions or changed
skips fail. See
[`validation/baseline-environment.md`](validation/baseline-environment.md).

## Validation (2026-09-15)

All 11 cases completed through Harbor 0.23.0 with the retained linux/amd64 image,
with zero errored trials and the expected reward in every case.

| Case | Agent / implementation | Expected reward | Result |
| --- | --- | --- | --- |
| `base` | `nop`, unchanged Base | 0 | 0; scope and PASS_TO_PASS pass; 17 behavior checks and 4 lifecycle checks fail because the requested behavior is absent. |
| `oracle` | `oracle`, reference patch | 1 | 1; all layers pass, including 18/18 contract and 4/4 lifecycle cases. |
| `alternative-event-journal` | `oracle`, independent event-journal patch applied to Base | 1 | 1; all layers pass, including 18/18 contract and 4/4 lifecycle cases. |
| `accept-stale-revision` | `oracle` + negative-control patch | 0 | 0; C06 and C15 detect acceptance of stale approvals. |
| `accept-extension-control` | `oracle` + negative-control patch | 0 | 0; C07 detects acceptance of extension-origin controls. |
| `replay-duplicate-approval` | `oracle` + negative-control patch | 0 | 0; C10 detects duplicate execution. |
| `allow-custom-planning-tools` | `oracle` + negative-control patch | 0 | 0; C02, C09, and L01 detect tools incorrectly enabled during planning. |
| `replay-approved-resume` | `oracle` + negative-control patch | 0 | 0; L02 detects execution replay after resume. |
| `resume-original-toolset` | `oracle` + negative-control patch | 0 | 0; L01 detects unrestricted tools after resuming a planning session. |
| `drop-approved-request-context` | `oracle` + negative-control patch | 0 | 0; C10 detects the approved snapshot missing from model-visible context. |
| `early-exit-zero` | `oracle` + negative-control patch | 0 | 0; incomplete behavior/lifecycle results are rejected despite a zero process exit. |

Both correct implementations passed 2,104 regression cases and retained the 50
original skips, without using the AuthStorage exception. The repeated-approval
and early-exit controls encountered the exact known Base assertion; their
intended behavior failures still determined reward 0.

[`validation/ci-cases.json`](validation/ci-cases.json) pins the patches and their
application order. Detailed results and negative-control rationale are in
[`validation/author-results.md`](validation/author-results.md) and
[`validation/wrong-controls.md`](validation/wrong-controls.md). These checks
establish verifier acceptance and rejection behavior, not coding-agent success
rates.

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

Before publication:

1. Provide a pullable immutable image. OS repositories and the Dockerfile
   frontend are not snapshot-pinned, so rebuilding later is not guaranteed to
   produce an identical image.
2. Clarify the invalid-submission error signal in `instruction.md`: C04
   currently requires a tool-error result (`isError=true`), while the instruction
   explicitly specifies unchanged plan state without naming that signal.
3. Use repeated independent coding-agent trials to measure difficulty and
   discrimination; construction checks and individual rollouts do not establish
   a reliable success rate.
