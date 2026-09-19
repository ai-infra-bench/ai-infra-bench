# pi-background-processes

**Status: staged (`staged-smoke-only`), task version 0.0.4.** Fully validated through the Harbor
entrypoint on a linux/arm64 build (Base 0, Oracle 1, one correct alternative 1,
12 negative controls 0, independent oracle challenge passed); the canonical
image is now built from `templates/pi-harbor-node` for linux/amd64 (CI's
platform, under qemu locally) and smoke-tested with Base/Oracle. `image_digest`
records that template build; the CI x64 runner has not built or published it
yet.

Version 0.0.2 (2026-09-16) rewrites the instruction as outcome requirements plus the tool and message contract, removing every mechanism it used to prescribe: the process-group and detached-stdio recipe, the hint that an extension may register a tool named `bash`, `pi.sendMessage`, pi's steering delivery, re-raising the signal, `SessionManager.getSessionDir()` with per-pi-process keying, writing logs as they arrive, and the built-in `bash` truncation limits and error strings (now: byte-for-byte what the built-in tool returns). The verifier observes behaviour only and is unchanged; the validation below and the real rollouts were made on the 0.0.1 wording.

Version 0.0.3 (2026-09-16) keeps the 0.0.2 requirements and restates them as an issue rather than a specification: motivation, the ask, the agreed interface, the behaviour we expect to see, and the lifecycle rules, with no mechanism hints added. Verifier unchanged.

Harness revision 2 (2026-09-17): the lifecycle suite keeps the runner's `VITEST*` variables out of the child pi it spawns. Version 0.0.4 (2026-09-16) restates the SIGTERM/SIGINT sentence as an unmistakable outcome (pi, interactive or headless, must still end after the signal) after two more rollouts left a headless pi running, and revises the verifier harness: the between-test drain now waits 300 ms and for an idle session, and a verifier prompt waits for an idle session, since the contract lets a wake start a turn at any idle moment and an implementation may report an exit shortly after the process died. Cases, oracle and controls unchanged.

Harness revision 3 (2026-09-17): the agent phase runs as the unprivileged `node` user while the verifier runs as root; the installed toolchain is root-owned so candidate code cannot rewrite the runner that produces the verifier's reports, and `tests/test.sh` rejects submissions that change pi source or the build/test toolchain (see the task review under `validation/`). Harness revision 4 (2026-09-18): `tests/test.sh` runs every suite that executes candidate code (pass-to-pass, contract, lifecycle) as the unprivileged `node` user too, so candidate code cannot rewrite the runner, interpreter or baseline during verification either; the reward file is written only by root; the image records the pass-to-pass baseline as `node` so it matches the candidate's run conditions (2158 tests, 0 environmental failures, 50 skipped). Verifier cases unchanged. Harness revision 5 (2026-09-19): what a submission changed is decided by content, never by git, because the checkout and its `.git` belong to the agent. `tests/check_scope.py` hashes pi core, the build/test toolchain and the existing test files against `tests/base-manifest.json` (derived from the Base commit, identical across platforms), and the build-generated files (the `dist/` trees the lifecycle suite runs, generated sources) against `/opt/pi-baseline/build-manifest.sha256`, which the image records root-owned at build time; it runs before the suites and again after them. This closes three bypasses reproduced on revision 4 (`validation/scope_bypass_probe.sh`): a core edit hidden with `git update-index --assume-unchanged`, an edit to the gitignored built pi core, and a `.git/config` `core.fsmonitor` hook that the verifier's own root `git status` executed as root (root no longer runs git in the checkout; the informational `agent-changes.patch` snapshot is taken as `node`). PASS_TO_PASS now runs only the Base test files named by the pinned baseline, so the scored report holds the Base inventory; the submission's own test files run right after and must pass (`candidate_tests_exit_code`). The rule itself is unchanged: scratch files and new files outside the protected paths are not penalised. New controls `control-scope-hidden-by-gitignore` and `control-built-dist-tampered` (expected 0). Image rebuilt (one added layer); verifier cases unchanged.

## What the agent does

Adds a background-process extension to [pi](https://github.com/earendil-works/pi)
at a pinned commit. Processes run in their own process group, stream logs to
disk, can wake the agent through pi's steering queue, survive `/reload`,
`/new`, `/fork`, and never outlive the pi process. The extension also overrides
the built-in `bash` tool: a command that goes silent for `stalledSec` seconds
is moved to the background automatically, and its next output line and its
exit wake the agent. See [`instruction.md`](instruction.md).

## Environment

- Base: `earendil-works/pi` @ `d981de1229ef899957bbe968bc8dcda02a21f477`
  (release v0.85.1, 2026-09-05T11:54:46Z), fetched by SHA with no tags or refs.
- `node:22.19.0-bookworm-slim` pinned by its multi-arch manifest-list digest,
  `npm ci` from the repository's own `package-lock.json`, `npm run build` so the
  published `dist/` entry points and the `pi` CLI exist offline.
- `fd` 10.2.0 from the pinned release tarball (Debian's 8.6 lacks the
  `--no-require-git` flag pi's find tool uses), `ripgrep` from Debian, so pi's
  tools-manager finds both on PATH and never downloads at runtime.
- `/opt/pi-baseline/`: pi's own coding-agent vitest suite run on Base inside the
  image (2158 cases, 50 skipped without keys, a few environmental failures
  recorded in `summary.json`). This is the PASS_TO_PASS baseline.
- The Dockerfile is generated from `templates/pi-harbor-node` (the Node
  counterpart of the vLLM template): `generate.py --check` verifies it, and
  `build.py` builds it from an empty context and writes `image-manifest.json`.
- CPU only, `no-network` for agent and verifier, agent timeout 10 h.
- No real model is ever contacted during verification: the image has no network,
  `test.sh` unsets every provider credential pi recognises and sets
  `PI_OFFLINE=1`, and the only model is pi's first-party faux provider. pi's
  key-gated suites therefore stay skipped and are pinned as skipped in the
  PASS_TO_PASS baseline.

## Verifier

`tests/test.sh` runs four layers; reward is 1 only if all pass.

| Layer | File | What it observes |
|---|---|---|
| PASS_TO_PASS | `tests/check_pass_to_pass.py` | In-image baseline verified against `tests/baseline-pins.json` (Base case inventory digest, key-gated skipped-set digest, failure cap, and the allowed set of environmental failures; identical on arm64 and amd64 builds, so it survives CI rebuilds while a rewritten baseline is rejected; `validation/baseline_pin_forgery_check.py` demonstrates the rejections); existing test files unchanged (`git diff` against Base); pi's full coding-agent suite (`--retry 2`, 4 workers) compared with the baseline: every case that passed on Base must pass, the skipped set must be identical, no new failures. |
| Contract (15 cases) | `tests/bg.contract.test.ts` | Real `AgentSession` + pi's faux provider + real fixture processes: tool results, custom wake messages and their order, OS process state, session-replacement runtime (`/new`, `/fork`), `/reload`, and the `bash` override (normal path unchanged; a silent command moves to the background and its next output and exit wake the agent). |
| Lifecycle (3 cases) | `tests/bg.lifecycle.test.ts` | Separate child pi processes built from `dist/`: normal exit and SIGTERM leave no managed process alive; a later pi process reads finished records from the session directory. |
| Integrity | `tests/check_junit.py` | Exact case inventory, zero failures/errors/skips, for the contract and lifecycle suites. |

The verifier files are copied into `packages/coding-agent/test/__verifier__/` at
verify time so vitest resolves workspace aliases; they never enter the image.
The LLM is the only substituted component.

## Validation (2026-09-14, local colima docker, linux/arm64)

| Case | Agent | Expected | Result |
|---|---|---|---|
| base | nop | 0 | 0 (contract 15/15 fail: `Tool bg_run not found`, built-in `bash` rejects `stalledSec`; lifecycle 3/3 same; PASS_TO_PASS n/a) |
| oracle | oracle | 1 | 1 (PASS_TO_PASS ok, contract 15/15, lifecycle 3/3) |
| alternative-class-manager-sparse-index | oracle agent + `validation/alternative-*.patch` | 1 | 1 (all layers pass, 115 s) |
| 12 negative controls | oracle + `validation/control-*.patch` | 0 | see `validation/controls-plan.md` |

Runs used Harbor 0.22.0 through `.github/scripts/task_ci.py` (`validate`,
`image-check`, `prepare-case`, `check-result`) exactly as CI does, minus the
GHCR cache and the x64 `hardware-check`. Logs and `verifier/` output for every
trial are kept on the curator's machine under `~/ai-infra-scratch/harbor-jobs/pi-background-processes/`; the summarised results are in `validation/e2e-evidence.json`.

Local pitfalls worth knowing: Harbor's `no-network` mode builds an egress
sidecar with `docker buildx` (the CLI plugin must be installed); colima shares
only `$HOME`, so Harbor job and case directories must live under it.

## Real-agent rollout (2026-09-14)

One claude-code + claude-opus-5 rollout (25 min, subscription OAuth, host
proxy) produced a 1.4 k-line submission that scored reward 0: PASS_TO_PASS and
lifecycle passed, contract 12/14 after judge fixes on the contract of that time.
The rollout exposed one contract contradiction (`bg_kill` vs the exit wake),
one harness defect (`runtime.dispose()` announced a process-level `quit`
between tests), one harness fragility (zombie processes counted as alive), and
one case that regulated implementation rather than outcome (merged wake
messages; removed together with its control). All are fixed and documented in
[`validation/rollout-2026-09-14-claude-code.md`](validation/rollout-2026-09-14-claude-code.md).
Run another with `tools/local_agent_rollout.sh` (credentials in
`~/.ai-infra-bench/rollout.env`).

A second rollout (Grok Build, grok-4.6, host `grok login` session via
`tools/harbor_agents/grok_build_oauth.py`, 33 min) scored 0 on the current
contract: PASS_TO_PASS pass, contract 15/15, lifecycle 2/3. Its `SIGTERM`
handler re-raises only when it is the sole listener, and so does the
`signal-exit` listener already present in pi, so a headless pi never exits.
See [`validation/rollout-2026-09-14-grok-build.md`](validation/rollout-2026-09-14-grok-build.md).
`tests/test.sh` now also saves the agent's diff to
`/logs/verifier/agent-changes.patch`.

A third rollout (Grok Build, grok-4.6, 31 min) on the 0.0.2 wording scored 0
the same way: PASS_TO_PASS pass, contract 15/15, lifecycle 2/3. Its signal
handlers stop the managed processes and then neither re-raise nor exit, so a
headless pi never terminates after `SIGTERM`. See
[`validation/rollout-2026-09-16-grok-build.md`](validation/rollout-2026-09-16-grok-build.md);
the submission is the expected-0 control `alt-grok-0.0.2-sigterm-listener`.

A fourth rollout (claude-code + claude-opus-5, 32 min) on the 0.0.3 wording scored 0:
PASS_TO_PASS pass, contract 10/15 as recorded, lifecycle 2/3. Four of the five contract
failures were a harness fragility (a late but contract-conforming exit wake spilled into
the next test's session and started a turn there; fixed in 0.0.4), one is a real defect
(the auto-background path breaks after a reload), and the lifecycle failure is the SIGTERM
clause again (the handler defers to other listeners). See
[`validation/rollout-2026-09-16-claude-code.md`](validation/rollout-2026-09-16-claude-code.md);
the submission is the expected-0 control `alt-opus-0.0.3-defer-and-reload`.

A fifth rollout (Grok Build, grok-4.6, 31 min) on the 0.0.4 wording is the first pass:
contract 15/15, PASS_TO_PASS pass, lifecycle 3/3 once the harness stopped leaking the
runner's `VITEST` variable into the child pi (the submission skips its exit hooks under
that variable; a real pi never carries it). Recorded reward 0, corrected 1. See
[`validation/rollout-2026-09-17-grok-build.md`](validation/rollout-2026-09-17-grok-build.md);
the submission is the expected-1 control `alt-grok-0.0.4-vitest-guard`.

A sixth rollout (Grok Build, grok-4.6, 26 min) on the 0.0.4 wording passed outright:
contract 15/15, lifecycle 3/3, PASS_TO_PASS pass, reward 1, re-verified twice under the
final harness. See
[`validation/rollout-2026-09-17-grok-build-2.md`](validation/rollout-2026-09-17-grok-build-2.md);
the submission is the expected-1 control `alt-grok-0.0.4-clean-pass`.

## Layout

```
pi-background-processes/
├── .gitattributes                 # patch files: no blank-at-eol check (as in the vLLM tasks)
├── instruction.md                 # agent-facing contract
├── task.toml                      # CPU, no-network, 10 h agent budget
├── environment/
│   ├── Dockerfile                 # generated from templates/pi-harbor-node: pinned source + Node workspace + PASS_TO_PASS baseline
│   ├── image-manifest.json        # image identity, installed versions, recorded baseline (written by build.py)
│   └── lock/{package-lock.json, manifest.json}
├── tests/                         # verifier (never in the agent image)
│   ├── test.sh, check_junit.py, check_pass_to_pass.py, case_contract.py
│   ├── baseline-pins.json         # semantic identity of /opt/pi-baseline (case inventory, skipped set, failure cap, allowed failures)
│   ├── bg_support.ts, bg.contract.test.ts, bg.lifecycle.test.ts
│   └── fixtures/{emit.mjs, grandchild.mjs, pi_child.mjs}
├── solution/
│   ├── oracle.patch               # extension (bg tools + bash override) + README + unit tests (1238 lines)
│   ├── solve.sh                   # git apply
│   └── README.md                  # design notes
└── validation/
    ├── ci-cases.json              # 1 correct alternative (reward 1) + 12 negative controls (reward 0), SHA-256 pinned
    ├── alternative-class-manager-sparse-index.patch  # materially different correct implementation (Dimension 6)
    ├── control-*.patch
    ├── controls-plan.md           # matrix with local and Harbor results
    ├── behavior-map.md            # contract clause -> case
    ├── independent_challenge.py   # curator-only: independently derived contract cases (runs independent_probe.mjs in the image)
    ├── independent_probe.mjs
    ├── baseline_pin_forgery_check.py  # curator-only: genuine baseline accepted, four forgeries rejected
    ├── rollout-2026-09-14-claude-code.md  # real-agent rollout 1 and the judge fixes it produced
    └── rollout-2026-09-14-grok-build.md   # real-agent rollout 2 (session-auth custom agent)
```

## Running

```bash
# CI-equivalent local run (python 3.12 for task_ci.py, Harbor 0.22.0); the same flow as CI, in one script:
# python3.12 tools/local_task_validation.py pi-background-processes ai-infra-bench/pi-background-processes:base-d981de1229ef
python3 templates/pi-harbor-node/generate.py --check tasks/pi-background-processes
python3 templates/pi-harbor-node/build.py --platform linux/amd64 tasks/pi-background-processes   # canonical tag ai-infra-bench/pi-background-processes:base-d981de1229ef
python3.12 .github/scripts/task_ci.py image-check --task pi-background-processes --image ai-infra-bench/pi-background-processes:base-d981de1229ef
# then prepare-case / harbor run / check-result per case as in .github/scripts/run_task_validation.sh

# Real agent rollout (credentials in ~/.ai-infra-bench/rollout.env; agent preinstalled in the image
# so Harbor skips its network install; host proxy forwarded, verifier phase offline):
tools/local_agent_rollout.sh pi-background-processes ai-infra-bench/pi-background-processes:rollout-cc claude-opus-5 0.05 claude-code
```

## Correct alternative and independent challenge

- `validation/alternative-class-manager-sparse-index.patch` is a materially
  different correct implementation: a class-based process manager in its own
  module, a log store with a sparse line index (one checkpoint per 512 lines)
  instead of a full in-memory offset table, per-process wake state instead of a
  global delivery queue, and unconditional signal re-raise. It was derived from
  the second real-agent rollout (grok-4.6) with its one defect fixed (the
  submission deferred SIGTERM to other listeners); provenance is documented in
  `validation/rollout-2026-09-14-grok-build.md`. It scores 1 through Harbor.
- `validation/independent_challenge.py` runs `independent_probe.mjs` inside
  the image against a candidate: relative `cwd` resolution with a Unicode error
  pattern and non-ASCII output, intermittent output keeping a `bash` command in
  the foreground, paging past the end of a log, and `bg_kill` on a finished
  process. None of these cases appear in the verifier suites. Oracle and the
  alternative both pass all eight checks.

## Remaining work before publication
1. Image publication through `publish-task-images.yml`. CI on the x64 runner is done: run 35258346225 (PR #92, head `b426b07`, 2026-09-17T18:21Z) built the Dockerfile natively (image sha256:33bb73df41a2…) and ran the full `validation/ci-cases.json` matrix green; the local amd64 build (`sha256:b44780bd36ba…`, task.toml `image_digest`) is not yet pushed to a registry.
   After the first native build, compare the image's `/opt/pi-baseline/summary.json` `failed_on_base` with `allowed_failures` in
   `tests/baseline-pins.json`: an environmental failure that is not listed makes Oracle score 0 with a `baseline_pin_problems` message, and
   the fix is to extend the pin (the pin is the union of every platform's Base failures). The CI run above passed this check.
2. Ten-dimension review: done 2026-09-17 (`validation/task-review-2026-09-17.md`), by the curator session; an independent second reviewer has not repeated it.
3. Repository: `templates/pi-harbor-node` is new with this task; a second pi
   task should exercise it before it is treated as stable.
