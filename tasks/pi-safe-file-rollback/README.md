# pi-safe-file-rollback

**Status: locally validated; image publication pending.** Version `0.0.4`
was validated through Harbor on the retained linux/amd64 image: Base 0,
Oracle and two correct implementation/interface controls 1, and nine negative
controls 0. Four complete saved answers were regraded without new model calls.
See [author evidence](validation/e2e-evidence.json),
[saved-answer evidence](validation/saved-answer-regrade.json), and the
[hardening record](validation/rollout-hardening.md).

**Platform.** The verifier runs on linux/amd64 only: `tests/baseline-pins.json` pins the amd64 `node_modules` tree, and `tests/process_supervisor.py` (the ptrace crash-injection supervisor) uses Linux/amd64 syscall numbers. On any other host `run_verifier.py` stops with `Unsupported verifier platform ...` and reward 0; build and validate with `--platform linux/amd64` on a Linux x64 machine (an arm64 Mac cannot run it, natively or emulated).

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
| PASS_TO_PASS | `tests/run_verifier.py` | All 2,158 original coding-agent cases remain in the inventory, with unchanged skips and no unaccepted regressions. Three legacy TUI session fixtures are adapted to the new public API; their assertions remain unchanged. |
| Stable auth regression | `tests/stable_auth_reload.test.ts` | A deterministic counterpart to the timestamp-sensitive Base AuthStorage assertion must pass. |
| Behavior (26 cases) | `tests/verify.py`, `tests/sdk_peer.mjs`, `tests/tui_case.py` | Real request boundaries, file and conversation restoration, partial Bash effects, process interruptions, conflict rejection, restart and branch isolation, execution gating, and SDK/RPC/terminal interfaces. |
| Interruption observation | `tests/process_supervisor.py`, `tests/scripted_provider.py` | Causal barriers and actual filesystem activity establish interruption points across Pi, Bash, and child processes. The observer does not restore files or session state. |
| Integrity | `tests/run_verifier.py`, `tests/drop_worker.cjs` | Independent scoring, protected reports, exact completed inventories, and rejection of missing results or early successful exits. |

The provider supplies model responses and records actual subsequent requests;
Pi's tools, filesystem, session persistence, and recovery run for real. Scoring
does not inspect private recovery journals or require a particular storage
layout or restoration order. Checkpoint metadata and list order are not graded;
actual file and conversation restoration are. The mapping is in
[`validation/behavior-map.md`](validation/behavior-map.md).

The three TUI fixture adaptations and their negative controls are documented in
[`validation/regression-fixtures.md`](validation/regression-fixtures.md).
One unrelated AuthStorage assertion has a narrowly defined accepted Base
failure signature and a mandatory stable counterpart; see
[`validation/base-auth-timestamp-evidence.md`](validation/base-auth-timestamp-evidence.md).

## Validation (2026-09-17)

All 13 author cases and four full saved-answer replays completed through Harbor
0.23.0 with zero errored trials. All author checks matched. Three of four original
saved-answer launcher checks matched: Sol xhigh was mistakenly configured to
expect 1, although prior review established 0 for its ENOTDIR defect. Its actual
reward remains 0; the original check exit 2 is preserved, and a separate read-only
result check against the correct expectation 0 passes. The table uses reviewed
expectations, not the mistaken launcher input. The author inventory
includes Base, Oracle, two correct controls, and nine negative controls. Inputs
were frozen before each run and checked afterward, including every prepared
case. All trials retain the original 2,158-case inventory and the separate
stable auth check; detailed outcomes and any narrowly accepted Base timestamp
failure are recorded in the linked evidence.

| Case | Expected | Reward | Behaviors passed |
| --- | --- | --- | --- |
| `base` | 0 | 0 | 0/26 |
| `oracle` | 1 | 1 | 26/26 |
| `alternative-blob-journal` | 1 | 1 | 26/26 |
| `minimal-checkpoint-metadata` | 1 | 1 | 26/26 |
| `memory-only` | 0 | 0 | 17/26 |
| `checkpoint-at-request-end` | 0 | 0 | 21/26 |
| `files-only` | 0 | 0 | 14/26 |
| `conversation-only` | 0 | 0 | 9/26 |
| `ignore-conflicts` | 0 | 0 | 23/26 |
| `skip-startup-recovery` | 0 | 0 | 19/26 |
| `abandoned-branch-included` | 0 | 0 | 24/26 |
| `early-process-exit-zero` | 0 | 0 | 1/26 |
| `missing-runtime-fork-gate` | 0 | 0 | 21/26 |
| Saved `traex-gpt55` | 0 | 0 | 2/26 |
| Saved `astra-xhigh` | 1 | 1 | 26/26 |
| Saved `sol-medium` | 0 | 0 | 19/26 |
| Saved `sol-xhigh` | 0 | 0 | 25/26 |

Saved-answer rewards belong to this verifier version. All four historical
rewards remain 0 in their original records; the source archives were unchanged.
The two repaired TUI fixtures from v0.0.2 and a third startup-input fixture now
supply the required disabled/ready API while preserving the original assertions.
Independent production mutations still trigger those assertions.

The new `runtime_fork_contract` calls the pinned SDK's real
`AgentSessionRuntime.fork`: a ready fork succeeds without a provider request;
recovery gates reject or explicitly cancel changes while preserving the session,
checked fixture files and effective conversation. A missing runtime fork guard
is now a declared negative control. Filesystem failure injection preserves Git
repository ownership and accepts complete preflight refusal as well as a
retryable pending restore. A public cancellation variant is exercised separately.

[CI cases](validation/ci-cases.json) pin complete Base-applicable control patches.
The [negative-control record](validation/wrong-controls.md),
[regression fixture record](validation/regression-fixtures.md), and
[hardening record](validation/rollout-hardening.md) explain their scope.
Earlier supervisor probes (33/33) are retained as historical evidence; they were
not rerun because the observer and retained image are unchanged. The
[artifact audit](validation/artifact-audit.json) and
[manifest](validation/artifact-manifest.json) bind final delivery files.

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
    ├── minimal-checkpoint-metadata.patch
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

Saved-answer replays demonstrate the recorded implementations under this
verifier. Repeated independent trials are needed to estimate solve rates or
compare agents; this control matrix does not establish practical difficulty.
