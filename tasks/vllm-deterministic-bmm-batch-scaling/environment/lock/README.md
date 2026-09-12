> Historical environment-build record. Hardware indices and verifier descriptions
> below describe the earlier build validation, not the current review. Current
> hardware assignment, behavioral coverage and measured results are recorded in
> `validation/review-report.md` and `validation/e2e-evidence.json`. This README is
> not copied by the Dockerfile and does not change the image build inputs.

# Environment lock for vllm-project/vllm#29345

## Upstream evidence

- PR: <https://github.com/vllm-project/vllm/pull/29345>
- Related issue: <https://github.com/vllm-project/vllm/issues/27433>
- Exact base: `b07555d26f4c7ad9a2d1ec45428a9d4287db612c`
- PR head: `bbb1e6d26634baf43d0be29ddb103ef6797c683c`
- The optimization replaces the Python-loop BMM with a Triton JIT kernel. The
  PR itself changes no vLLM C++/CUDA source, but the base is 283 commits after
  v0.11.1 and the intervening history does include native changes.

## Immutable inputs

- Official toolchain/runtime image: `vllm/vllm-openai:v0.11.1`
- Image manifest digest:
  `sha256:d5b12dfb74d605615f8b29ebafaa52294c118bcac7bc9e941785c4108fdb913a`
- Git helper image: `alpine/git:2.49.1`
- Git helper manifest digest:
  `sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26`
- Source archive URL:
  `https://codeload.github.com/vllm-project/vllm/tar.gz/b07555d26f4c7ad9a2d1ec45428a9d4287db612c`
- Source archive SHA-256:
  `5f5d48bb58d898d89d65bb4310b916f3472f84db0cb17f994203084e3aafce1f`
- Source archive bytes: `17447112`

Prepare the generated archive beside the Dockerfile and verify it before the
offline build:

```bash
curl --retry 10 --retry-all-errors -fL \
  -o environment/vllm-source.tar.gz \
  https://codeload.github.com/vllm-project/vllm/tar.gz/b07555d26f4c7ad9a2d1ec45428a9d4287db612c
cd environment
sha256sum -c lock/vllm-source.sha256
```

The archive is not committed. The Dockerfile re-verifies its full digest,
builds with `--network none`, and runtime validation uses `--network none`.
Proxy settings belong only to the host/daemon and are not embedded.

## Source, native, and Git binding

The full exact-base source is placed at `/workspace/repo`; `.pth` prepends that
tree, and `cp --no-clobber` fills only files absent from source with the
official wheel's native/generated runtime surface. Both `vllm.__file__` and
`vllm._C.__file__` must resolve below `/workspace/repo/vllm`. This rejects the
old wheel plus single-file-link construction: every Python/Triton source edit
in the exact tree is authoritative.

This environment has a **known native-origin limitation**. A full exact-SHA
native build was attempted with `pip install --no-build-isolation --no-deps -e`
and the image's nvcc/cmake/ninja toolchain. It failed after 384 seconds at
CMake configure because offline `FetchContent` attempted to clone CUTLASS
v4.2.1. Source inspection shows four more unconditional CUDA external projects
(Triton kernels v3.5.0, FlashMLA, QuTLASS, and vLLM flash-attention), none
retained in the official image. The final native `_C` therefore originates
from official v0.11.1 release commit
`439368496db48d8f992ba8c606a0c0b1eebbfa69`, exposed in the image label
`ai-infra-bench.vllm-native-origin`. The BMM under evaluation is Python/Triton
JIT and the PR changes no native source, so it is directly executable, but
this image must not be claimed as a general exact-base native build.

The codeload archive contains no upstream Git objects. A separate build stage
fetches only the exact Base and its parent history; the sanitized `.git` is
then bound to the byte-locked worktree. `HEAD` equals the declared Base, the
worktree is clean, and remotes, remote refs, tags, reflogs, fetch metadata,
shallow boundaries, unreachable objects, and the known future commit are
absent. The non-root `agent` (UID/GID 1000) owns the repository.
