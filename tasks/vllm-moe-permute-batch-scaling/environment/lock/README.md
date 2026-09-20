# Locked environment inputs

The exact pre-PR source is vLLM commit
`dc917cceb877dfd13f98c538c4c96158047d98bd`, canonical Git tree
`89beecb205e031cbb82e2eea9d2cd0f350135b8c`. Its codeload archive is locked
by byte size and SHA-256. A separate stage fetches only the exact Base and its
parent history, sanitizes Git metadata, and binds that `.git` to the archive
worktree. The final image has the Base at `HEAD` and no remotes, remote refs,
tags, reflogs, fetch metadata, shallow boundary, unreachable objects, or known
future commit.

The latest official release before the base commit is v0.14.0. It matches the
base source's PyTorch 2.9.1 and CUDA 12.9 requirements. The linux/amd64 image is
manifest-digest pinned. No `VLLM_TARGET_DEVICE=empty` build is used.

PR 32892 modifies the native `_moe_C` extension. Consequently the Dockerfile
does not reuse the release image's `_moe_C`. It compiles the target from the
exact source for SM80 and installs it under `/workspace/vllm/vllm`. The build retains
CMake, Ninja, the build directory, and locked Cutlass 4.2.1 headers so the
non-root agent can rebuild after changing candidate CUDA sources.

CMake 3.31.10 is installed from a SHA-256-locked wheel. Git 2.49.1 and its musl runtime are copied from the digest-pinned Alpine Git stage. The source is exposed through `vllm-candidate-source.pth`; only the focused `_moe_C` extension is built and installed with CMake. There is no editable pip installation. Versions and immutable identities are recorded in `environment.json`.

The task needs no model or dataset. The reproduction creates DeepSeek-V2-lite
MoE dimensions directly (`64` experts, top-k `6`, hidden size `2048`, alignment
`128`) and uses FP8 only as one-byte storage copied by the kernel. It performs
no FP8 Tensor Core arithmetic, so the assigned A100 SM80 is eligible.
