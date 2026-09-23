# pi Harbor Node Dockerfile template

Environment template for agent-harness tasks on [pi](https://github.com/earendil-works/pi)
(`earendil-works/pi`, a Node 22 npm workspace), with a prebuilt default and an
explicit source workspace mode. Each task keeps its own
self-contained `environment/Dockerfile`, generated from this template and the
task's `task.toml` (`base_commit`, `dependency_cutoff`) plus the checked-in
dependency lock. The layout and conventions (generate / build / lock scripts,
empty build context, provenance labels, image manifest) are the same as
`templates/vllm-harbor-all-in-one`, so the two kinds of task are reviewed and
built the same way.

What the default prebuilt image contains:

- pi's monorepo at the pinned commit, fetched by SHA with no tags, remotes, or
  reflogs (the source stage CI's `image-check` expects).
- `node:22.19.0-bookworm-slim` pinned by its multi-arch manifest digest, `npm ci`
  from the repository's own `package-lock.json` (its sha256 is embedded in the
  Dockerfile and checked at build time), then pi's build **without network**
  (`RUN --network=none npm run build:offline`, pi's own root script that skips `generate-models`) so the published
  `dist/` entry points and the `pi` CLI work offline. The model catalog that
  pi's normal build would regenerate from live APIs comes from the published
  `@earendil-works/pi-ai` package of the same release, pinned by sha256 (see
  "Model catalog" below).
- `fd` from its pinned release tarball and `ripgrep` from Debian, so pi's
  tools-manager never downloads at runtime; `python3` for verifier helpers.
- `PI_OFFLINE=1`, `PI_TELEMETRY=0`, `PI_NO_LOCAL_LLM=1`: no model is ever
  contacted; pi's first-party faux provider is the only model in verification.
- `/opt/pi-baseline/`: pi's coding-agent vitest suite run on the unmodified Base
  inside the image, with a summary of the environmental failures. This is the
  PASS_TO_PASS baseline; the task pins its identity in `tests/baseline-pins.json`.

## Commands (repository root)

```bash
# Materialize the lock (package-lock.json at base_commit + lock manifest):
python3 templates/pi-harbor-node/lock.py tasks/pi-background-processes

# Generate or check the task Dockerfile:
python3 templates/pi-harbor-node/generate.py tasks/pi-background-processes
python3 templates/pi-harbor-node/generate.py --check tasks/pi-*

# Build with an empty context and write environment/image-manifest.json.
# CI validates on x64; on an arm64 host pass --platform linux/amd64 (qemu).
python3 templates/pi-harbor-node/build.py --platform linux/amd64 tasks/pi-background-processes

# Exercise rendering, ownership selection and rejected configuration:
python3 -m unittest discover -s templates/pi-harbor-node/tests -v
```

Edit the template, not a generated Dockerfile. `generate.py --check` is a
curator-side check (CI builds the checked-in Dockerfile as is); run it before
committing a template change. The builder sends an empty context to BuildKit,
so tests, the Oracle, and curator files cannot enter the image; the baseline
checker script is embedded in the Dockerfile with a heredoc `COPY` for the same
reason. `build.py` writes `environment/image-manifest.json` in the repository
format (`templates/harbor-task/README.md`, "Image manifest"): the retained
`image_id` and the hashes of `Dockerfile`, `lock/package-lock.json` and
`lock/manifest.json`, plus `pi-template.json` when configured. Installed versions and the baseline summary are printed as an
`IMAGE {...}` line for the build log; they are build records, not task files.

After every rebuild, compare that line's `pass_to_pass_baseline.failed_on_base`
with the task's `tests/baseline-pins.json` `allowed_failures`: a platform may
show an environmental failure the pin does not list yet, and the fix is to
extend the pin.

## Agent user and toolchain ownership

By default, the rendered image leaves the checkout owned by the `node` user and the installed toolchain (`node_modules`, `node`, `python3`, `bash`) owned by root and read-only for others; tasks set `[agent].user = "node"` so the agent cannot rewrite the test runner the verifier (root) executes. vite's transient config bundles go to `node_modules/.vite-temp` and `.vite`, which belong to the selected agent user; verifiers remove them before running. Root's git is configured with `safe.directory /workspace/pi`. Pair this with a verifier-side check that the submission did not change pi source or the build/test toolchain (see the pi task `tests/test.sh` scope check).

Tasks that already use the reviewed Node 22.23.2 runtime and the `agent` account
can preserve both with `environment/pi-template.json`:

```json
{
  "node_image": "node:22.23.2-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5",
  "agent_user": "agent",
  "source_cli": true,
  "npm_ignore_scripts": true,
  "workspace_mode": "source"
}
```

These keys and the optional `strace_version` below are the only accepted keys.
Missing keys retain the Node 22.19.0 / `node`
defaults, both boolean options set to `false`, and `workspace_mode: "prebuilt"`;
no configuration file preserves the existing generated Dockerfile
bytes. `node_image` accepts only the two reviewed, digest-pinned Node images in
`generate.py`, and must agree with the lock manifest's recorded image. The
generator also accepts the older manifest format with platform notes after the
image reference. `lock.py` uses this same runtime selection for new manifests.

`agent_user` accepts only `node` or `agent`. Selecting `agent` creates that account
without removing the image's existing `node` account, and uses it consistently
for checkout ownership, Vite directories and the upstream baseline run. The Node
interpreter is still invoked as `node`. The generator requires the task's
`[agent].user` to match; keep the verifier's candidate execution user aligned
with it as well. The toolchain and baseline remain root-owned. This configuration
does not change the Pi commit, dependency lock, model catalog source or empty
build context. The workspace mode below determines whether dist is built.

`source_cli: true` adds a root-owned `/usr/local/bin/pi` wrapper from the inline
script in `source-cli.Dockerfile`. The wrapper sets `TSX_TSCONFIG_PATH` and
the TSX loader in `NODE_OPTIONS`, then executes
`node /workspace/pi/packages/coding-agent/src/cli.ts` with the original arguments.
In prebuilt mode this option does not set image-wide Node options; vitest and
other Node processes keep their normal environment. Source mode also preserves
the original global loader, as described below. The wrapper is installed and checked with
`pi --version` without network before the ownership and native baseline steps,
so the baseline sees the same CLI command as the final image.

`npm_ignore_scripts: true` preserves tasks whose installation uses
`npm ci --ignore-scripts --no-audit --no-fund`; it does not add native compilation
dependencies or change the lock. `lock.py` records the same install policy in
the manifest's `resolver` field. Both options require JSON booleans; strings and
numbers are rejected. With either option omitted or `false`, its generated
Dockerfile content remains unchanged.

`strace_version: "6.1-0.1"` optionally installs the reviewed Debian Bookworm
strace package, with an exact package-version check during the image build.
No other value is accepted. Omitting the key preserves the generated Dockerfile
bytes and does not install strace. This is general syscall observation tooling;
it adds no task-specific fixture, candidate restriction, or tracing privilege.
Only `pi-subagent-live-messaging` currently enables it. The verifier must still
check tracing permissions in the actual runtime; installation alone does not
prove that observation works under Harbor's process and container settings.

## Source workspace mode

`workspace_mode` accepts only `prebuilt` (default) or `source`. Source mode
requires both `source_cli: true` and `npm_ignore_scripts: true`. It validates the
frozen model catalog with Pi's own `node packages/ai/scripts/check-model-data.ts`
and checks that tracked sources remain unchanged. It does **not** compile dist
or require dist entry points. The source CLI, offline path-utils smoke test,
fd/ripgrep installation, complete native baseline and root-owned toolchain
protections remain enabled. The baseline failure allowance is unchanged.

Source mode sets the original image-wide values before catalog checks, smoke
tests and the native baseline:
`TSX_TSCONFIG_PATH=/workspace/pi/tsconfig.json` and
`NODE_OPTIONS=--import=/workspace/pi/node_modules/tsx/dist/loader.mjs`.
These are required for dynamic imports and child Node processes to resolve
workspace sources instead of nonexistent `chord/dist` or `pi-tui/dist` modules.
A loader confined to the `pi` wrapper does not preserve those behaviors.
Compare individual native test outcomes across image changes; a total below the
failure allowance does not justify new failures in previously passing cases.

The root-owned build manifest still hashes generated workspace files; source
mode requires at least 40 model catalog JSON entries instead of 500 dist entries.
Its image carries `ai.infra.bench.workspace-mode=source`, and `build.py` records
`workspace_mode: "source"`, `dist_built: false` and `pi: "… (workspace source)"`
in its `IMAGE` log record. This does not constitute a successful dist build.

For frozen Pi `71dca871bc80b6bc97be37f0ca3189399d651fff`, the unmodified
`npm run build:offline` passes catalog validation but reports TS2322 at
`packages/ai/src/api/google-shared.ts:402`: `FinishReason.TOO_MANY_TOOL_CALLS` is
not assignable to `never`. Source mode preserves the original source execution
contract without changing that code, dependency lock or TypeScript checks; the
compiler failure remains a recorded limitation.

## Scope check by content

The checkout and its `.git` belong to the agent, so a verifier must not ask git what changed (`git update-index --assume-unchanged`, `.gitignore`, `.git/info/exclude` hide edits; `dist/` is gitignored; and git run as root in the checkout executes whatever `.git/config` names, e.g. `core.fsmonitor`). Two manifests replace it:

- `tests/base-manifest.json`, written by `python3 templates/pi-harbor-node/base_manifest.py <image> tasks/<task>...`: SHA-256 of the Base files under the protected paths and the existing test tree. It depends on the Base commit only; regenerate it when `base_commit` changes.
- `/opt/pi-baseline/build-manifest.sha256`, recorded root-owned by the image build: SHA-256 of the untracked files the build generated in the checkout (the `dist/` trees, generated model data), whose bytes depend on the build.

`tests/check_scope.py` in the pi tasks compares the workspace with both, before and after the suites. Root never runs git in the checkout.

## Model catalog

pi's `npm run build` runs `generate-models --strict`, which fetches model catalogs from live APIs (models.dev, OpenRouter, Vercel AI Gateway, NVIDIA NIM) and deletes the tracked `<provider>.models.ts` of any provider those APIs no longer list. An image built that way depends on its build date: two builds a few days apart carried different catalogs and bundles, and on 2026-09-19 every fresh build broke (`kimi-coding` disappeared upstream, `kimi-coding.models.ts` was deleted, pi no longer compiled), while cached builds kept working.

The template therefore takes `packages/ai/src/providers/data` from the published `@earendil-works/pi-ai` tarball of the release the base commit belongs to (`PI_AI_VERSION`, `PI_AI_TARBALL_SHA256`), checks that `packages/ai/package.json` has that version, and builds with network disabled; pi's own `check:model-data` validates the data against the tracked sources, and the build fails if any tracked file changes.

For 0.85.1 the base commit `d981de1229ef` is the "Release v0.85.1" commit itself (committed 2026-09-05T11:54:46Z, which is the tasks' `dependency_cutoff`). npm published the package at 12:05:47Z, 11 minutes after the cutoff, with a catalog generated at 11:58:56Z. It is the build of the base commit, not later work: its 177 `dist/*.js` files are byte-identical to this image's build of the base commit (0.85.0: 175 of 177), so it reveals nothing the agent could not build itself. The 0.85.0 package predates the cutoff but lacks `gpt-6-astra`, the headline addition of 0.85.1 that the base commit's generator and ai tests reference, a source/catalog combination that never existed upstream. A task on another base commit must set the two ARGs for its release and record the same reasoning.
