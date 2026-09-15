# Docker build and reproduction evidence: vLLM PR #29999

> Historical v1.0 validation. Task v1.1 uses the production layer factory and
> owner-provenance anti-lazy cases without prescribing a constructor keyword;
> the revised verifier has not yet been rerun.
>
> Provenance supersession: task v1.2.2 now retains the exact upstream Base at
> `HEAD` with sanitized parent history. Image IDs and Git assertions below are
> historical and are not evidence for the current environment; rebuild and
> `image-check` remain mandatory.

## Status

**Environment, runtime, and profile-path reproduction validated on A100.**

The exact reported multi-worker deployment was not recreated: this validation
was allocated one A100 GPU (`GPU 1`). Instead, the probe executes the same
`FusedMoEModularKernel.forward -> _fused_experts -> _allocate_buffers` profile
branch with real CUDA tensors and the real Triton MoE implementation. It uses a
valid DP=2 + EP `VllmConfig` in `ForwardContext`, then reproduces the worker
lifecycle gap in which the process-global config has ended. This is materially
stronger than the earlier constructor/mock-only test, but it is not evidence of
a complete distributed service launch.

No model or dataset is needed for this lifecycle bug. The probe generates
small deterministic CUDA tensors (4 experts, 4 tokens, hidden size 64) and
executes the actual fused-MoE kernel; therefore there is no external model/data
cache or model/data digest to record.

The final container runs as `agent` (UID/GID 1000), not root. The complete
runtime worktree is a clean, writable Git repository with one synthetic commit
on `benchmark-base` and zero remotes.

## Host and daemon

- Host: A100 server, NVIDIA A100-SXM4-40GB, physical GPU 1
- Remote task directory:
  `/data/ai-infra-bench/survey-builds/vllm-pr-29999`
- Required isolated daemon:
  `DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock`
- The daemon data-root is
  `/data/yaoyaoyao/pr34183-cuda-build/docker-data`; the default daemon was not
  used.
- Tag: `ai-infra-bench/vllm-pr-29999:base`

Every `docker pull`, `build`, `run`, `inspect`, and `history` command in this
validation exported that `DOCKER_HOST`. No prune was run and no unrelated image
was deleted.

## Immutable inputs

The official base was pulled through the host-owned daemon proxy and resolved
to:

```text
vllm/vllm-openai:v0.12.0@sha256:6766ce0c459e24b76f3e9ba14ffc0442131ef4248c904efdcbf0d89e38be01fe
base image bytes: 8931755554
vLLM: 0.12.0
torch: 2.9.0+cu129
CUDA runtime: 12.9
```

The offline build also uses this immutable helper stage because the official
runtime intentionally omits Git:

```text
alpine/git:2.49.1@sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26
```

Only the Git executable, its subcommands, and required musl libraries are
copied. The helper is not the final runtime base.

Exact PR base source:

```text
commit: 2902c348265639de300c95cbcae1c26486f57ac7
archive bytes: 17572523
sha256: 12a2dd5777029f342c5379c4b22ead2255912f832f98726692b5dbf5132256de
```

The proxy is daemon/host state only. `docker history --no-trunc` was searched
for the proxy host, proxy variables, and credential placeholders and returned
no match.

## Offline build

After the official image and exact source archive were cached, the measured
cold build used no network:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
cd /data/ai-infra-bench/survey-builds/vllm-pr-29999/context
DOCKER_BUILDKIT=0 docker build --no-cache --network none \
  -t ai-infra-bench/vllm-pr-29999:base .
```

Result:

```text
BUILD_STATUS=0
BUILD_SECONDS=416
image ID: sha256:f7382292aea8fc5aacbe84f77271d3a4685a45ad5813a6570702e78525bbabd7
image bytes: 9455436535
label source commit: 2902c348265639de300c95cbcae1c26486f57ac7
configured user: agent
```

The build log is retained at
`/data/ai-infra-bench/survey-builds/vllm-pr-29999/docker-build.log` and its
machine-readable timing summary at `docker-build-summary.txt`.

The build-time binding check printed:

```text
0.12.0 /workspace/repo/vllm/__init__.py /workspace/repo/vllm/_C.abi3.so
```

A separate runtime audit confirmed that the source archive contributed no
upstream Git metadata, while the final generated repository has exactly one
synthetic commit, zero remotes, and clean status. It also confirmed the import
still resolves to that tree and all five offline flags are set. As UID 1000,
the `agent` user successfully wrote a new file in the worktree and `git status`
reported it as untracked, proving ordinary coding-agent diff/status workflows
are functional.

## Real CUDA profile-path reproduction

The baseline was run with the physical GPU 1 exposed as the container's single
CUDA device and with runtime networking disabled:

```bash
export DOCKER_HOST=unix:///data/yaoyaoyao/pr34183-cuda-build/docker.sock
docker run --rm --network none --gpus device=1 \
  -v /data/ai-infra-bench/survey-builds/vllm-pr-29999/validation/profile_warning_probe.py:/probe.py:ro \
  --entrypoint /usr/bin/python3 \
  ai-infra-bench/vllm-pr-29999:base /probe.py
```

Observed baseline result:

```text
cuda_device=NVIDIA A100-SXM4-40GB
source_has_fix_api=False
valid_profile_warned=False norm=6865.378906
lifecycle_gap_profile_warned=True norm=6865.378906
genuine_missing_config_warned=True
PROFILE_WARNING_PROBE=PASS
```

This provides all three controls:

1. With a valid config installed globally, the real CUDA profile forward does
   not warn.
2. With the same valid config reachable through `ForwardContext` but not the
   process-global slot, the exact base emits the spurious warning.
3. A direct request with genuinely no config still emits the warning, so
   globally suppressing or downgrading the log cannot satisfy the check.

The identical output norm in cases 1 and 2 confirms the warning is a config
lifecycle defect, not a CUDA kernel failure. Full output is retained at
`profile-warning-probe.log`.

## Fix-path control

To prove candidate edits in `/workspace/repo` are live, the official PR diff
was downloaded outside the image, SHA-256 checked as
`ce7b4731adfff73933c366689e953114c818f2ef149bdc8db46ea69a517220c5`,
and applied only inside a disposable `--network none` GPU container. It is not
part of the base image or Docker context.

The same probe then reported:

```text
source_has_fix_api=True
valid_profile_warned=False norm=6865.378906
lifecycle_gap_profile_warned=False norm=6865.378906
genuine_missing_config_warned=True
PROFILE_WARNING_PROBE=PASS
```

All five upstream patch files applied to `/workspace/repo`; the profile warning
changed as expected while CUDA output and the true-missing-config warning were
preserved. Full output is retained at `patched-profile-warning-probe.log`.

## Construction-guide feedback

- A task whose symptom occurs in a deep runtime branch should distinguish
  “unit control”, “real branch execution”, and “full service reproduction”. A
  mocked constructor test alone is insufficient, while a real CUDA kernel
  probe can be acceptable evidence when the exact distributed topology is not
  available—provided the limitation is explicit.
- Warning-removal tasks need both a valid-state no-warning control and a
  genuinely missing-state warning control. Otherwise global suppression is an
  easy invalid shortcut.
- For main-branch PRs between releases, record why the nearest official image
  is ABI-compatible with the exact source SHA. Here the image creation date,
  vLLM 0.12.0 runtime, torch 2.9.0, and CUDA 12.9 were all checked rather than
  inferred from the tag alone.
- “No upstream Git metadata” is not enough for a coding task: the final image
  must also provide a clean, writable, one-commit synthetic repository and a
  usable Git binary, while running the agent as non-root.
- If no model or dataset is semantically required, explicitly record that the
  cache/digest requirement is not applicable; do not add a synthetic download
  merely to fill the field.
