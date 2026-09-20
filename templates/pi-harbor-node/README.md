# pi Harbor Node Dockerfile template

Environment template for agent-harness tasks on [pi](https://github.com/earendil-works/pi)
(`earendil-works/pi`, a Node 22 npm workspace). Each task keeps its own
self-contained `environment/Dockerfile`, generated from this template and the
task's `task.toml` (`base_commit`, `dependency_cutoff`) plus the checked-in
dependency lock. The layout and conventions (generate / build / lock scripts,
empty build context, provenance labels, image manifest) are the same as
`templates/vllm-harbor-all-in-one`, so the two kinds of task are reviewed and
built the same way.

What the generated image contains:

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
```

Edit the template, not a generated Dockerfile. `generate.py --check` is a
curator-side check (CI builds the checked-in Dockerfile as is); run it before
committing a template change. The builder sends an empty context to BuildKit,
so tests, the Oracle, and curator files cannot enter the image; the baseline
checker script is embedded in the Dockerfile with a heredoc `COPY` for the same
reason. `build.py` records `image_id` in the manifest; copy it to
`task.toml` `image_digest` (the repository audit requires them to match).

After every rebuild, compare the manifest's `pass_to_pass_baseline.failed_on_base`
with the task's `tests/baseline-pins.json` `allowed_failures`: a platform may
show an environmental failure the pin does not list yet, and the fix is to
extend the pin.

## Agent user and toolchain ownership

The rendered image leaves the checkout owned by the `node` user and the installed toolchain (`node_modules`, `node`, `python3`, `bash`) owned by root and read-only for others; tasks set `[agent].user = "node"` so the agent cannot rewrite the test runner the verifier (root) executes. vite's transient config bundles go to `node_modules/.vite-temp` and `.vite`, which are node-owned; verifiers remove them before running. Root's git is configured with `safe.directory /workspace/pi`. Pair this with a verifier-side check that the submission did not change pi source or the build/test toolchain (see the pi task `tests/test.sh` scope check).

## Scope check by content

The checkout and its `.git` belong to the agent, so a verifier must not ask git what changed (`git update-index --assume-unchanged`, `.gitignore`, `.git/info/exclude` hide edits; `dist/` is gitignored; and git run as root in the checkout executes whatever `.git/config` names, e.g. `core.fsmonitor`). Two manifests replace it:

- `tests/base-manifest.json`, written by `python3 templates/pi-harbor-node/base_manifest.py <image> tasks/<task>...`: SHA-256 of the Base files under the protected paths and the existing test tree. It depends on the Base commit only; regenerate it when `base_commit` changes.
- `/opt/pi-baseline/build-manifest.sha256`, recorded root-owned by the image build: SHA-256 of the untracked files the build generated in the checkout (the `dist/` trees, generated model data), whose bytes depend on the build.

`tests/check_scope.py` in the pi tasks compares the workspace with both, before and after the suites. Root never runs git in the checkout.

## Model catalog

pi's `npm run build` runs `generate-models --strict`, which fetches model catalogs from live APIs (models.dev, OpenRouter, Vercel AI Gateway, NVIDIA NIM) and deletes the tracked `<provider>.models.ts` of any provider those APIs no longer list. An image built that way depends on its build date: two builds a few days apart carried different catalogs and bundles, and on 2026-09-19 every fresh build broke (`kimi-coding` disappeared upstream, `kimi-coding.models.ts` was deleted, pi no longer compiled), while cached builds kept working.

The template therefore takes `packages/ai/src/providers/data` from the published `@earendil-works/pi-ai` tarball of the release the base commit belongs to (`PI_AI_VERSION`, `PI_AI_TARBALL_SHA256`), checks that `packages/ai/package.json` has that version, and builds with network disabled; pi's own `check:model-data` validates the data against the tracked sources, and the build fails if any tracked file changes.

For 0.85.1 the base commit `d981de1229ef` is the "Release v0.85.1" commit itself (committed 2026-09-05T11:54:46Z, which is the tasks' `dependency_cutoff`). npm published the package at 12:05:47Z, 11 minutes after the cutoff, with a catalog generated at 11:58:56Z. It is the build of the base commit, not later work: its 177 `dist/*.js` files are byte-identical to this image's build of the base commit (0.85.0: 175 of 177), so it reveals nothing the agent could not build itself. The 0.85.0 package predates the cutoff but lacks `gpt-6-astra`, the headline addition of 0.85.1 that the base commit's generator and ai tests reference, a source/catalog combination that never existed upstream. A task on another base commit must set the two ARGs for its release and record the same reasoning.
