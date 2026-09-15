# pi-plan-mode

Development task for review. The native amd64 image and both implementations
have been built and checked; final Harbor results are recorded separately in
`validation/e2e-evidence.json`. The branch and image have not been published.

## What the agent does

Enhance pi's existing Plan Mode example extension so approval identifies the
exact session, plan, and revision that the user reviewed. The change includes
explicit plan submission, interactive and RPC controls, stale-approval
rejection, exact restoration of the prior tool selection, and normal idle
session resume without repeating execution. The coding agent produces a patch
to pi; pi itself is the target repository, not the agent being ranked. See
[`instruction.md`](instruction.md) for the authoritative contract.

The task allows changes inside the existing Plan Mode extension, its README,
the existing `plan-mode-extension.test.ts`, and new coding-agent tests. Core,
dependencies, build configuration, unrelated extensions, and unrelated tests
remain unchanged. Planning semantics intentionally differ from the old example:
repeating `/plan` no longer restores writing, and arbitrary custom tools are
not enabled during planning.

## Environment

- Pi Base: `earendil-works/pi` at
  `d981de1229ef899957bbe968bc8dcda02a21f477` (v0.85.1).
- Dependency cutoff: `2026-09-05T11:54:46Z`; install the Base's original npm
  lock verbatim with `npm ci`.
- Generated from the task-local `environment/build/Dockerfile.template`, derived
  from `pi-harbor-node`: pinned Node 22.19.0 bookworm-slim,
  prebuilt pi workspace, fd 10.2.0, ripgrep, and Python for verifier helpers.
- CPU only: 4 CPUs, 8 GiB RAM, 20 GiB storage; agent budget 10 hours, verifier
  budget 1 hour; agent user `pi-agent`, workdir `/workspace/pi`; verifier
  coordinator runs as root and candidate test workers run as UID 65534.
- Runtime is offline. The verifier uses pi's first-party faux provider and
  installed development tools, with no real model requests. Building the image
  still requires access to the pinned source, registries, and package mirrors.
- The empty build context excludes task tests, reference solutions, and
  validation documents from the agent image. The template records the upstream
  coding-agent test baseline under `/opt/pi-baseline/`.

The actual image ID is recorded in `environment/image-manifest.json` and
`task.toml`. The image grants editing access to the allowed extension and tests,
and provides writable scratch/cache locations for normal upstream test commands.
Dependencies, Git metadata and core configuration remain protected. The verifier
freezes submitted sources, discards candidate caches, and keeps its coordinator,
scripts and final reports outside the worker's write permissions. This does not
claim complete protection against arbitrary code manipulating assertions inside
the same test worker.

## Verification contract

The intended boundary is:

```text
supported user input or a model tool call
  -> real extension loading, AgentSession input/tool dispatch and plan state
  -> observable control entries, tool results, approved execution message
  -> normal close and resume through real file-backed session storage
```

Only model responses and user UI choices may be scripted. The extension,
dispatcher, input-source handling, persistence, and execution scheduling must
run for real. Reward is binary: all required behavior, unaffected regressions,
and completion checks must pass. A successful candidate process exit alone is
insufficient.

PASS_TO_PASS must account for the task's explicit permission to update
`packages/coding-agent/test/plan-mode-extension.test.ts`: do not treat its old
toggle/custom-tool expectations as immutable regressions. Keep the Plan Mode
utilities and every unrelated Base regression protected. A trusted verifier
outside the candidate-running child checks completed case inventories and
final reward; early-success-exit controls must run through Harbor.

There are 18 contract checks (including one grading-permission precondition)
and four genuine cross-process lifecycle checks. The regression inventory is
2,154 Base cases after projecting out the four deliberately replaced legacy
Plan Mode tests. Skips, environmental failures, controls and actual run results
are recorded in the validation evidence rather than described as all passing.
One unrelated original AuthStorage assertion was independently reproduced on
untouched Base. It remains in the inventory and raw reports, and qualifies as a
known Base failure only when every reported attempt matches its exact pinned
error. Other failures, skips, missing cases and malformed reports still fail;
see [`validation/baseline-environment.md`](validation/baseline-environment.md).

## Layout

```text
pi-plan-mode/
├── instruction.md                       # Agent-facing behavior contract
├── task.toml                            # Frozen target, resources and budgets
├── environment/
│   ├── Dockerfile                       # Generated pinned Pi/Node environment
│   ├── image-manifest.json              # Written by the actual image build
│   ├── build/                          # This task's frozen recipe and helpers
│   │   ├── Dockerfile.template         # Pi baseline plus task permissions
│   │   ├── generate.py                 # Render or check environment/Dockerfile
│   │   └── build.py                    # Empty-context build and provenance
│   └── lock/{package-lock.json,manifest.json}
├── tests/                               # Verifier-only scenarios and scoring
├── solution/                            # Reference patch and solve.sh
└── validation/                          # Controls and actual construction evidence
    └── upstream-history.md              # Public history, applicability and leakage risk
```

## Building and running

Use Python 3.11 or newer for the build helpers. The task-local builder invokes
the generator with the same Python interpreter. Run from the benchmark repository root:

```bash
python3 templates/pi-harbor-node/lock.py tasks/pi-plan-mode
python3 tasks/pi-plan-mode/environment/build/generate.py
python3 tasks/pi-plan-mode/environment/build/generate.py --check
python3 tasks/pi-plan-mode/environment/build/build.py --platform linux/amd64
```

The lock helper is unchanged shared infrastructure. Generation and building are
task-local: use the commands above instead of the shared `generate.py --check`
for this task. The frozen template retains the `pi-agent` account, the exact
editable extension/test directories, writable Vite caches, and optional
`APT_MIRROR`. Edit this task's template when changing its environment; do not
regenerate it from the generic shared template, which lacks these permissions.

The builder accepts `--builder`, `--network`, repeatable `--allow`, and repeatable
`--build-arg` for local build infrastructure. These arguments are recorded in the
image manifest, so supply only non-secret values. They do not enable network
access during agent execution or verification.

Moving the recipe did not change any byte of `environment/Dockerfile` or the
retained image. Its historical header and `pi-harbor-node` image label identify
the original template lineage. The existing image manifest and build-provenance
record retain the command actually used for that build; future builds record the
new task-local command and template path. The frozen template has the same hash
as the original build's `template_sha256`.

After recording the built image identity and completing the solution/verifier
artifacts, use the repository's existing CI helpers. `prepare-case` injects the retained
image into a temporary task copy, avoiding an unintentional rebuild:

```bash
python3 .github/scripts/task_ci.py validate pi-plan-mode
python3 .github/scripts/task_ci.py image-check --task pi-plan-mode \
  --image ai-infra-bench/pi-plan-mode:base-d981de1229ef
python3 .github/scripts/task_ci.py prepare-case --task pi-plan-mode \
  --image ai-infra-bench/pi-plan-mode:base-d981de1229ef \
  --case oracle --output /tmp/pi-plan-mode-oracle
harbor run --path /tmp/pi-plan-mode-oracle --agent oracle --env docker \
  --jobs-dir ./harbor-jobs --job-name pi-plan-mode-oracle --n-concurrent 1
python3 .github/scripts/task_ci.py check-result \
  --result ./harbor-jobs/pi-plan-mode-oracle/result.json --expected-reward 1
```

Prepare `--case base` separately and use agent `nop`; it must receive 0 for a
missing target behavior, not an infrastructure failure. Run every declared
alternative and negative control the same way. Record the exact Harbor version
used; the development machine currently has Harbor 0.23.0, whereas the
background-task evidence used 0.22.0. The development host requires an
author-only launcher for a mirrored kernel-probe image; see
[`validation/harbor-environment.md`](validation/harbor-environment.md).

On the development host, a complete author matrix can be started from
`/data00/home/xingjunqian/ai-infra-bench-plan-mode` with a new output directory:

```bash
PATH=/data00/home/xingjunqian/harbor-workspace/author-tools/bin:$PATH \
python3 tasks/pi-plan-mode/validation/run_author_matrix.py \
  --image sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda \
  --output /data00/home/xingjunqian/harbor-workspace/pi-plan-mode/my-review-run \
  --workers 3 \
  --harbor /data00/home/xingjunqian/harbor-workspace/pi-plan-mode/harbor-mirrored
```

Add `--cases base oracle` for only the two primary author checks. The matrix
script refuses to reuse an existing output directory, preserving earlier logs.

A real-agent trial uses the same prepared environment with an available solver
and its model endpoint configured for the agent phase. For example, after
preinstalling the solver and supplying credentials through Harbor's supported
configuration:

```bash
harbor run --path /tmp/pi-plan-mode-oracle --agent codex --model <model-id> \
  --env docker --jobs-dir ./harbor-jobs --job-name pi-plan-mode-codex \
  --n-concurrent 1 --allow-agent-host api.openai.com
```

The endpoint and solver settings must match the actual provider; this example
does not assert that a solver login or rollout has been completed. Keep the
verifier offline and leave solution/validation artifacts hidden during solving.

## Completed author checks

The final 11-case Harbor matrix completed without environment errors: Base
received 0; Oracle and an independently written event-journal implementation
received 1; all eight incorrect implementations received 0 for their intended
behavior defects. Both correct implementations passed all 18 contract and four
lifecycle checks, with 2,154 regression cases collected and 50 original skips.
Neither correct implementation triggered the documented original AuthStorage
assertion in this final run. See
[`validation/author-results.md`](validation/author-results.md) for the per-case
results, known Base observations and raw evidence references.

The development worktree is `/data00/home/xingjunqian/ai-infra-bench-plan-mode`,
branch `agent/pi-plan-mode`. Changes are uncommitted and unpushed, awaiting user
review. Real solver trial results are kept separately from author-validation evidence.

## Provenance and remaining acceptance

The benchmark branch is based on `agent/base` at
`781120385bff838a5ff50abf6de50f3d4e2965a3`. Initial task construction used main
`9a5d7fee81b151a362b13a67587a12fc8cc00296` and the Pi helpers from
`agent/pi-background-processes` at
`f7689fecbca0725aa06fab1a8dd238a25eae0652`.
The shared `templates/pi-harbor-node/` files now match `agent/base` exactly.
This task keeps its permission configuration and build-network options under
`environment/build/`, so they do not change other Pi tasks' generated environments.
The separate artifact-audit change still honors each control's declared
`apply_after` value when checking patches in fresh containers.
See `validation/template-migration.json` for the relocation checks and preserved
runtime artifact identities.

Plan Mode code and related fixes are already public. The task is an explicit
enhancement with a stronger approval contract, not a claim of an unseen feature
or contamination-free evaluation. See
[`validation/upstream-history.md`](validation/upstream-history.md). This task
uses a retained local image for author validation. OS repositories and the
Dockerfile frontend are not snapshot-pinned, so rebuilding later is not guaranteed
byte-identical; see `validation/build-provenance.json`. Before publication,
provide a pullable immutable image or fix the remaining build inputs, and run
real coding-agent trials to measure difficulty and discrimination. Author checks
alone do not establish solver success rates.
