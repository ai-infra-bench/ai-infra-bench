# Environment and accepted-solution lock

## Authoritative Base and Oracle

FlashInfer/vLLM survey metadata originally recorded contributor Base
`31a719bcd37a195107711dc8b498288e49ef8576` and head
`beae1ecede055847be8980528b2b7fc2d9e2fab9`. That pair is a valid
ancestor/head development diff, but it is not the accepted repository state.

PR #34246 was squash-merged as one-parent commit
`4f6eed3bd4a92c6bd513460ee85b917d6df88a17`. The published task therefore
uses the authoritative accepted pair:

- Agent Base (squash parent): `36d7f19897843c9cbdb701ba88d0f2c29954fe44`;
- Base tree: `647523aac911ae44a1dcaab79ef66d58290b478e`;
- Base archive bytes: `31,020,571`;
- Base archive SHA-256:
  `8e71d0480773b8532f7397e52257e5600b0ef0ff56654eba5e78afc48be0cbab`;
- evaluator Oracle: `4f6eed3bd4a92c6bd513460ee85b917d6df88a17`;
- Oracle tree: `774873b4f62efa1653458b46b142f4a579a84eaa`;
- Oracle archive bytes: `31,019,742`;
- Oracle archive SHA-256:
  `09dfea032b28890ee9be138390ac27b4115c653118b902763720f7bb5e2fc734`.

GitHub compare reports `ahead_by=1`, `behind_by=0`, merge base equal to the
Agent Base, and the accepted nine-file `+54/-51` patch. The evaluator patch is
13,753 bytes with SHA-256
`6f4c23941397f5ca178724efd6a002a20ebe5b4075e0319265ebc50ad2d29256`.
It is stored only under `solution/`, outside the environment build context.

## Issue and behavioral mapping

Issue #38257 reports a deterministic OOM in
`_merge_multimodal_embeddings` for Qwen3-VL-235B on 8xH100. A maintainer
identified `masked_scatter_` as creating a large temporary copy; the reporter
then confirmed that PR #34246 removed the OOM and allowed a concurrent ChartQA
run. The issue closed with `Fixed by #34246`.

The PR keeps multimodal masks on CPU and uses direct indexed assignment. Its
added CUDA unit test asserts that this production primitive does not
synchronize, relying on the CPU-mask indexing behavior available since
PyTorch 2.9. The A100 hidden verifier uses the same production function and
preserves the exact causal boundary: CUDA target/source tensors, CPU boolean
mask, in-place ordered assignment, synchronization rejection, allocator
measurement, and strict cardinality errors. No model or dataset is required.

## Image and native scope

- Runtime image: `vllm/vllm-openai:v0.19.0`;
- immutable digest:
  `sha256:d9a5c1c1614c959fde8d2a4d68449db184572528a6055afdd0caf1e66fb51504`;
- image creation time: `2026-04-03T00:07:37.341665339Z`;
- PyTorch: `2.10.0+cu129`;
- Git helper: `alpine/git:2.49.1` at
  `sha256:c0280cf9572316299b08544065d3bf35db65043d5e3963982ec50647d2746e26`.

The accepted Base predates v0.19.0 by roughly two days. The earlier v0.18.1
image lacks `_C_stable_libtorch`, so the first survey image mixed seven
v0.18.1 extensions with one v0.19.0 extension and emitted four duplicate
registration diagnostics. That image is retired.

The Harbor environment takes all eight native extensions and generated
`_version.py` from the single internally consistent v0.19.0 image. Every path
is a regular ELF (except `_version.py`) and is verified by `native.sha256`
before copying. Candidate Python always resolves to the accepted Base tree.
This eliminates mixed-native duplicate registration; it does not claim exact
Base native provenance for unrelated operators.

The scored merge primitive is Python plus PyTorch indexing and invokes no vLLM
native operator. The verifier nevertheless imports both `vllm._C` and
`vllm._C_stable_libtorch`, rejects duplicate-registration diagnostics, and
checks that their loaded paths remain inside the candidate tree. Native-heavy
vLLM tasks must not reuse this environment without an exact source build.

## Agent and network boundary

The source archive is hash-verified and its reconstructed Git tree must equal
the canonical Base tree. The image contains one synthetic commit, no remotes,
a clean worktree, and a non-root `agent` owner. The environment build context
is exactly `tasks/vllm-pr-34246/environment`; `tests/` and `solution/` cannot
enter the image.

Build networking is used only for the immutable source archive. Runtime is
`--network none`, with Hugging Face, datasets, pip, and telemetry offline.
