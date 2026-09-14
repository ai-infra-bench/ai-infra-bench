# pi Harbor Node Dockerfile template

Environment template for agent-harness tasks on [pi](https://github.com/earendil-works/pi)
(`earendil-works/pi`, a Node 22 npm workspace). It is the Node counterpart of
`templates/vllm-harbor-all-in-one`: each task keeps its own self-contained
`environment/Dockerfile`, generated from this template and the task's
`task.toml` (`base_commit`, `dependency_cutoff`) plus the checked-in
dependency lock.

What the generated image contains:

- pi's monorepo at the pinned commit, fetched by SHA with no tags, remotes, or
  reflogs (the same source stage as the vLLM template).
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
