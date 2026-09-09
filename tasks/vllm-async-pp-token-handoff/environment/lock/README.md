# Environment lock

Survey item: `vllm__pr__32618`.

## Source and ancestry

- Upstream: `https://github.com/vllm-project/vllm.git`
- PR: `https://github.com/vllm-project/vllm/pull/32618`
- Follow-up to: `https://github.com/vllm-project/vllm/pull/32359`
- Tracking issue: `https://github.com/vllm-project/vllm/issues/32701`
- Base: `8ebf372e9d612a325f54aadf5c0c3c6588b6afa3`
- Base date: `2026-01-28T17:36:56Z`
- Base subject: `[CI] Whisper tests enforce_eager=False (#33098)`
- Head inspected: `6ce90d085df26ad2cf823cc61eea8375a97ca2b7`
- Recorded squash merge: `3e440786afe763e892e12125ee7529f95f141c54`
- Squash parent: `8bdd3979d8c2f15feb475485ba1af1917cefbe5a`
- Base archive SHA-256:
  `22c309000b09e9824a0ba5f5837e2b76a32f001b964f4153343cb030e44ba2b7`
- Head archive SHA-256:
  `f945e4e74be312ae48f8f0ae3620ca6de807055d8c8971d8091133ce7427ddfa`
- Canonical forced-add base tree:
  `27422138dd790ac7992e774d438e0bf84d546c01`
- Runtime Git: exact upstream Base at `HEAD` with parent history, branch
  `benchmark-base`, and no remote, remote refs, tags, reflogs, fetch metadata,
  shallow boundary, unreachable objects, or known future commit

GitHub compare reports the base as the exact merge-base: head is 17 commits
ahead and zero behind. GitHub's recorded merge commit is a squash commit with
one parent, so it must not be interpreted as a two-parent base/head merge.

## Official runtime donor

- Image: `vllm/vllm-openai:v0.14.1`
- Linux/amd64 digest:
  `sha256:8e67731819426f7df194e5a0dfd6649d3aa3474f80c44f75b1e8711e76f8030a`
- Published: `2026-01-24T20:29:27Z`, four days before the base cutoff
- Runtime: Torch `2.9.1+cu129`, CUDA `12.9`
- Exact Git packages: `git=1:2.34.1-1ubuntu1.17`,
  `git-man=1:2.34.1-1ubuntu1.17`, `liberror-perl=0.17029-1`

Exact base Python replaces the donor package. The machine-readable donor
manifest locks eight native files and two generated flash-attention wrappers;
neither production target intersects these artifacts.

## Validation scope

The public Dev uses a real two-rank NCCL process group on two A100 GPUs. It
invokes the production `GPUModelRunner` PP broadcast/receive methods directly,
checks the sampled-token tensor, request-index reconstruction, discard mask,
and local output placeholder update. No fake transport replaces NCCL.

This focused verifier does not claim scheduler re-entry, a model forward, PP4
serving, accuracy, or performance. Full acceptance requires the original
Qwen3-30B-A3B FP8 model, four pipeline stages, GSM8K/lm-eval, random serving
inputs, 128 concurrent prompts, and paired async/non-async measurements.
