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
  Dockerfile and checked at build time), `npm run build` so the published
  `dist/` entry points and the `pi` CLI work offline.
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
