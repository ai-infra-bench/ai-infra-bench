> Historical environment-build record. Hardware indices and verifier descriptions
> below describe the earlier build validation, not the current review. Current
> hardware assignment, behavioral coverage and measured results are recorded in
> `validation/review-report.md` and `validation/e2e-evidence.json`. This README is
> not copied by the Dockerfile and does not change the image build inputs.

# Environment lock for vllm-project/vllm#29999

## Upstream evidence

- PR: <https://github.com/vllm-project/vllm/pull/29999>
- PR base: `2902c348265639de300c95cbcae1c26486f57ac7`
- PR head: `e7beecc8d7974a17d66871eeb3bbd6277a82aa02`
- Reported symptom: DP+EP workers repeatedly log `Current vLLM config is not
  set.` while preparing the fused-MoE profile run.
- The PR base and the v0.12.0 release tag diverged (`base` is 56 commits ahead
  and 12 behind in GitHub's compare result). The v0.12.0 official image was
  created on 2025-12-03, the day the PR opened, and contains vLLM 0.12.0,
  torch 2.9.0+cu129, and CUDA 12.9. It is the closest official release runtime
  for the exact base source; the source override is required rather than
  treating the image tag as the candidate code.

## Immutable inputs

- Official image: `vllm/vllm-openai:v0.12.0`
- Manifest digest:
  `sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe`
- Git helper image: `alpine/git:2.49.1`
- Git helper manifest digest:
  `sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26`
- Exact source archive:
  `https://codeload.github.com/vllm-project/vllm/tar.gz/2902c348265639de300c95cbcae1c26486f57ac7`
- Source archive SHA-256:
  `12a2dd5777029f342c5379c4b22ead2255912f832f98726692b5dbf5132256de`

Prepare the generated build input beside the Dockerfile, then verify it:

```bash
curl --retry 10 --retry-all-errors -fL \
  -o environment/vllm-source.tar.gz \
  https://codeload.github.com/vllm-project/vllm/tar.gz/2902c348265639de300c95cbcae1c26486f57ac7
cd environment
sha256sum -c lock/vllm-source.sha256
```

The archive is not committed. After the immutable base has been pulled and
the archive cached, build uses `--network none`. Runtime validation also uses
`--network none`; offline environment variables disable package, model,
dataset, and telemetry network access.

## Source/runtime binding and sanitization

The official image supplies the compiled CUDA extensions. The exact base
source is extracted at `/workspace/repo`, and a `.pth` file prepends that tree
to Python's import path. `cp --no-clobber` adds only wheel-only/generated files
to it, so candidate edits remain authoritative. The build fails unless both
`vllm.__file__` and the discoverable `vllm._C` resolve below
`/workspace/repo/vllm`.

The codeload archive brings no upstream Git metadata. A separate build stage
fetches only the exact Base and its parent history; the sanitized `.git` is
then bound to the byte-locked worktree. `HEAD` equals the declared Base, the
worktree is clean, and remotes, remote refs, tags, reflogs, fetch metadata,
shallow boundaries, unreachable objects, and the known future commit are
absent. The final process user is the non-root `agent` (UID 1000), which owns
the worktree and repository.
