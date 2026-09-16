# pi-safe-file-rollback

**Status: locally validated; image publication pending.** Version `0.0.2` was
validated through Harbor on a retained linux/amd64 image: Base 0, Oracle 1,
one correct alternative 1, and eight negative controls 0. A saved Codex /
GPT-6 Astra xhigh answer also passes. Results are in
[`validation/e2e-evidence.json`](validation/e2e-evidence.json) and
[`validation/saved-answer-regrade.json`](validation/saved-answer-regrade.json).

## What the agent does

Adds opt-in safe rollback to [pi](https://github.com/earendil-works/pi) at a pinned
commit. Checkpoints precede top-level requests. After an interruption, users can
restore workspace files and the effective conversation together, including
partial changes from `edit`, `write`, and `bash`. Recovery must preserve earlier
dirty content and Git state, reject conflicting human edits, and finish an
interrupted rollback before normal execution resumes. The benchmark evaluates
the coding agent's patch to pi. See [`instruction.md`](instruction.md) for the
authoritative contract and public SDK, RPC, and terminal interfaces.

The feature belongs in production code with appropriate tests. Dependency
manifests, lockfiles, generated model data, and build/test configuration remain
unchanged; existing tests must not be changed to suppress regressions.

## Environment

- Base: `earendil-works/pi` at `d981de1229ef899957bbe968bc8dcda02a21f477`
  (v0.85.1); dependency cutoff `2026-09-05T12:05:48Z`.
- Pinned Node 22.19.0 bookworm-slim, `npm ci` with the Base's original lockfile,
  and a prebuilt pi workspace. `fd` 10.2.0, ripgrep, and Python are installed.
  Runtime model data comes from the hash-pinned pi-ai 0.85.1 release with the
  same Git head; building does not query current model catalogs.
- The Dockerfile is generated from `environment/build/Dockerfile.template`.
  The builder uses an empty context and records the image identity in
  `environment/image-manifest.json`; `task.toml` pins that identity.
- CPU only: 4 CPUs, 8 GiB RAM, 20 GiB storage; agent timeout 10 hours and
  verifier timeout 1 hour. The agent runs as `node` in `/workspace/pi`.
- The environment has no network by default. Verification uses a scripted local
  HTTP provider and makes no external model requests. Building the image
  requires access to the pinned source and packages.
- Task tests, reference solutions, and validation artifacts are excluded from
  the image. The original regression baseline is retained in `/opt/pi-baseline/`.

The agent can edit production sources and run ordinary offline builds and tests.
The verifier checks protected dependencies and configuration, rehydrates the
pinned regression fixtures, and freezes sources before observation. Candidate
workers run as UID 65534, separate from the root coordinator and its reports.

## Verifier

`tests/test.sh` runs the following layers. Reward is 1 only if every required
layer passes; a successful candidate process exit alone is insufficient.

| Layer | File | What it observes |
| --- | --- | --- |
| Build and protected inputs | `tests/run_verifier.py`, `tests/baseline-pins.json` | Installed dependencies and protected build inputs match their pins; the candidate builds offline. |
| PASS_TO_PASS | `tests/run_verifier.py` | All 2,158 original coding-agent cases remain in the inventory, with unchanged skips and no unaccepted regressions. Two legacy TUI session stubs are adapted to the new public API; their assertions remain unchanged. |
| Stable auth regression | `tests/stable_auth_reload.test.ts` | A deterministic counterpart to the timestamp-sensitive Base AuthStorage assertion must pass. |
| Behavior (25 cases) | `tests/verify.py`, `tests/sdk_peer.mjs`, `tests/tui_case.py` | Real request boundaries, file and conversation restoration, partial Bash effects, process interruptions, conflict rejection, restart and branch isolation, execution gating, and SDK/RPC/terminal interfaces. |
| Interruption observation | `tests/process_supervisor.py`, `tests/scripted_provider.py` | Causal barriers and actual filesystem activity establish interruption points across Pi, Bash, and child processes. The observer does not restore files or session state. |
| Integrity | `tests/run_verifier.py`, `tests/drop_worker.cjs` | Independent scoring, protected reports, exact completed inventories, and rejection of missing results or early successful exits. |

The provider supplies model responses and records actual subsequent requests;
Pi's tools, filesystem, session persistence, and recovery run for real. Scoring
does not inspect private recovery journals or require a particular storage
layout or restoration order. The mapping is in
[`validation/behavior-map.md`](validation/behavior-map.md).

The two TUI fixture adaptations and their negative controls are documented in
[`validation/regression-fixtures.md`](validation/regression-fixtures.md).
One unrelated AuthStorage assertion has a narrowly defined accepted Base
failure signature and a mandatory stable counterpart; see
[`validation/base-auth-timestamp-evidence.md`](validation/base-auth-timestamp-evidence.md).

## Validation (2026-09-16)

All 11 author-control cases and the saved-answer replay completed through
Harbor 0.23.0 with zero errored trials and the expected rewards. Every trial
passed 2,108 original regression cases, retained 50 existing skips, and passed
the separate stable auth test. None used the AuthStorage exception.

| Case | Agent / implementation | Expected reward | Result |
| --- | --- | --- | --- |
| `base` | `nop`, unchanged Base | 0 | 0; build and PASS_TO_PASS pass; required rollback interfaces are absent. |
| `oracle` | `oracle`, reference patch | 1 | 1; all layers pass, including 25/25 behavior cases. |
| `alternative-blob-journal` | `oracle`, alternative storage/restoration patch | 1 | 1; all layers pass, including 25/25 behavior cases. |
| `memory-only` | `oracle`, Base-applicable negative control | 0 | 0; 17/25 behaviors pass; restart loses recovery state. |
| `checkpoint-at-request-end` | `oracle`, Base-applicable negative control | 0 | 0; 20/25 pass; interrupted requests lack a checkpoint. |
| `files-only` | `oracle`, Base-applicable negative control | 0 | 0; 14/25 pass; revoked messages remain in effective context. |
| `conversation-only` | `oracle`, Base-applicable negative control | 0 | 0; 9/25 pass; workspace changes remain. |
| `ignore-conflicts` | `oracle`, Base-applicable negative control | 0 | 0; 22/25 pass; conflicting human edits are overwritten. |
| `skip-startup-recovery` | `oracle`, Base-applicable negative control | 0 | 0; 19/25 pass; restart leaves recovery unresolved. |
| `abandoned-branch-included` | `oracle`, Base-applicable negative control | 0 | 0; 23/25 pass; non-ancestor checkpoints remain eligible. |
| `early-process-exit-zero` | `oracle`, Base-applicable negative control | 0 | 0; only disabled behavior passes; incomplete execution is rejected. |
| Saved Codex / GPT-6 Astra xhigh answer | Replay of the complete unchanged answer | 1 | 1; 25/25 behaviors pass after the regression-fixture correction. |

[`validation/ci-cases.json`](validation/ci-cases.json) pins complete patches that
apply directly to Base; controls do not require a preceding Oracle application.
Rationale and detailed results are in
[`validation/wrong-controls.md`](validation/wrong-controls.md) and the evidence
linked above. The saved answer's historical reward under version 0.0.1 remains
recorded as 0; its version 0.0.2 reward is 1. Regrading generated no new answer.

Independent supervisor probes passed 33/33 executions on the retained image
without additional Docker privileges. The
[`task review`](validation/review-report.md) records fixture, image, statement,
and scoring checks; the [`artifact audit`](validation/artifact-audit.json) and
[`manifest`](validation/artifact-manifest.json) bind the final delivery files.

## Layout

```text
pi-safe-file-rollback/
├── instruction.md                       # Agent-facing behavior contract
├── task.toml                            # Frozen target, resources, and budgets
├── environment/
│   ├── Dockerfile                       # Generated Pi/Node environment
│   ├── image-manifest.json              # Image identity and build metadata
│   ├── build/
│   │   ├── Dockerfile.template          # Offline build and task permissions
│   │   ├── generate.py                  # Render or check the Dockerfile
│   │   └── build.py                     # Empty-context image build
│   └── lock/{package-lock.json,manifest.json}
├── tests/                               # Verifier scenarios and scoring
├── solution/                            # Reference patch and solve.sh
└── validation/                          # Alternative, controls, and evidence
    ├── ci-cases.json
    ├── alternative-blob-journal.patch
    ├── behavior-map.md
    ├── e2e-evidence.json
    ├── saved-answer-regrade.json
    └── run_author_matrix.py
```

## Building and running

Use Python 3.11 or newer, Docker with Buildx, and Harbor. Run these commands from
the benchmark repository root:

```bash
python3 tasks/pi-safe-file-rollback/environment/build/generate.py --check
python3 tasks/pi-safe-file-rollback/environment/build/build.py --platform linux/amd64
```

Use the task's own generator and builder to preserve its offline build and
permissions. The builder accepts `--builder`, `--network`, repeatable `--allow`,
and repeatable `--build-arg`. Recorded option values omit host-specific details;
build options do not enable verifier networking.

To validate the task and run Oracle against an existing image:

```bash
python3 .github/scripts/task_ci.py validate pi-safe-file-rollback
python3 .github/scripts/task_ci.py image-check --task pi-safe-file-rollback \
  --image ai-infra-bench/pi-safe-file-rollback:base-d981de1229ef
python3 .github/scripts/task_ci.py prepare-case --task pi-safe-file-rollback \
  --image ai-infra-bench/pi-safe-file-rollback:base-d981de1229ef \
  --case oracle --output ./harbor-cases/pi-safe-file-rollback-oracle
harbor run --path ./harbor-cases/pi-safe-file-rollback-oracle --agent oracle --env docker \
  --jobs-dir ./harbor-jobs --job-name pi-safe-file-rollback-oracle --n-concurrent 1
python3 .github/scripts/task_ci.py check-result \
  --result ./harbor-jobs/pi-safe-file-rollback-oracle/result.json --expected-reward 1
```

`prepare-case` binds the selected image in a separate task copy. Use `--case base`
with agent `nop` to check the expected reward 0. Coding-agent trials must also
start from a fresh Base copy, with solutions and validation artifacts hidden
during solving. Configure required model endpoint access only for the agent
phase.

The full author matrix can be run with:

```bash
python3 tasks/pi-safe-file-rollback/validation/run_author_matrix.py \
  --image ai-infra-bench/pi-safe-file-rollback:base-d981de1229ef \
  --output ./harbor-validation/pi-safe-file-rollback \
  --workers 3
```

Use a new output directory for each run. Add `--cases base oracle` for the two
primary controls. `--harbor` selects a Harbor executable or external launcher.

## Evaluation limits and remaining work

The contract covers a local Linux workspace with exclusive execution ownership.
Power loss, concurrent writers, external service effects, cross-session
checkpoint transfer, redo, and arbitrary sibling switching are excluded.
Existing public rollback implementations do not establish novelty or
contamination-free evaluation; the author-side
[`reference comparison`](validation/public-reference-comparison.md) records
observed differences without defining the scoring contract. The verifier's
isolation and probes cover the tested mechanisms, not every possible encoding
or arbitrary manipulation within a candidate test worker.

Public image delivery remains pending. The publication workflow must validate
the image it publishes and retain a pullable immutable reference. OS repositories
and the Dockerfile frontend are not snapshot-pinned, so a later rebuild is not
guaranteed to produce identical bytes.

The saved answer demonstrates one successful implementation. Repeated
independent trials are needed to estimate model solve rates or compare agents;
the control matrix and a single replay do not establish practical difficulty.
