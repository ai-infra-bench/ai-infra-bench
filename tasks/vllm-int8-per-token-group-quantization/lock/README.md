# Source and environment lock

This task is derived from vLLM PR [#21476](https://github.com/vllm-project/vllm/pull/21476), “CUDA Kernel for Int8 Per Token Group Quant”. The benchmark starts from parent commit `14bf19e39f601163265b7c7d58d972b8a83d8896`; the isolated contributor head used by the task metadata, solution patch, and oracle control is `2e25870f8445f9531a7fa9fb8f144bb68e4ab6e6`. GitHub's resulting merge commit is `75d29cf482193478e0093b99e1bc51ca1332722f`; it is provenance only and is not used as the oracle identity.

The parent commit was created on 2025-07-23, four days before the v0.10.0 release. The environment therefore uses the nearest following official `vllm/vllm-openai:v0.10.0` image, pinned to Docker content digest `sha256:05a31dc4185b042e91f4d2183689ac8a87bd845713d5c3f987563c5899878271`. The Dockerfile rebuilds the PR's complete candidate native path, `vllm._C`, and the Python package from the selected exact source archive. Unrelated extensions are copied no-clobber from the same-version official image and labeled as scoped donor binaries; they are not presented as exact-source builds.

Locked build inputs:

| Input | Immutable revision | SHA-256 |
|---|---|---|
| vLLM benchmark base | `14bf19e39f601163265b7c7d58d972b8a83d8896` | `ef6429c4011bb3955ac9249833aa0a82f36b7855dcad7ac556deb4849d5f3339` |
| vLLM oracle control | `2e25870f8445f9531a7fa9fb8f144bb68e4ab6e6` | `12a475fafd3aa1fcb0fa1eae1daf48a68f59a63fd0b69bca06dfefe8455703b6` |
| NVIDIA CUTLASS | tag `v4.0.0` | `44a121c5878827875856c175ebe82e955062e37cd61fcdf31ebe2e8874f2fc5c` |
| vLLM FlashAttention | `1c2624e53c078854e0637ee566c72fe2107e75f4` | `cca19d7e53af08aa6d6f0c4fd9dd78d30314497e38fb03b1368b3d5a77ab4b5c` |
| FlashAttention CUTLASS submodule | `62750a2b75c802660e4894434dc55e839f322277` | `78816d6c6d97793b5b59ef2a702174cb85b78dfcefc8fe2489964de2e42f17d2` |
| vLLM FlashMLA | `575f7724b9762f265bbee5889df9c7d630801845` | `42ebf11c1a4cd17c4221705de5cff4fcaedf29a9dbdfcb8f2459dc550faf66f7` |

All archives come from the corresponding GitHub repository archive endpoint and
are verified before extraction. GitHub source archives omit Git submodule
contents, so FlashAttention's pinned CUTLASS submodule is a separate locked
input. The Docker build needs network access only to download these immutable
URLs; SHA-256 verification occurs before any archive is extracted. CMake is
then pointed at the extracted immutable sources, preventing FetchContent from
silently changing the build. Evaluator runtime remains offline.

The byte-locked Base source is paired with Git metadata fetched in an isolated
stage. The final repository retains the exact upstream Base at `HEAD` and its
parent history, while remotes, remote refs, tags, reflogs, fetch metadata,
shallow boundaries, unreachable objects, and the known Oracle commit are
absent.

The task is intentionally A100-scoped. The new kernel uses the existing generic 8-bit CUDA implementation and has no Hopper-only instruction or minimum-sm90 guard. The baseline CMake supports sm80. We compile with `TORCH_CUDA_ARCH_LIST=8.0`, then confirm the runtime device capability is `(8, 0)` before correctness or performance claims.
