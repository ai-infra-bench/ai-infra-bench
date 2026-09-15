# Environment lock

This environment packages survey item `vllm__pr__34179` at the exact base
revision. Native donor scope is also available in machine-readable form in
`native-donor.json`.

## Source

- Upstream: `https://github.com/vllm-project/vllm.git`
- PR: `https://github.com/vllm-project/vllm/pull/34179`
- Linked roadmap issue: `https://github.com/vllm-project/vllm/issues/32455`
- Base: `be3af2d29e2507f32b2190fe015cd6609b348caa`
- Base date: `2026-02-17T23:18:18Z`
- Base subject: `[Model Runner V2] Further simplification for PP (#34724)`
- Head inspected: `18bdb6535bf5c2bea4c8c66870fad02879757995`
- Exact base archive SHA-256:
  `1f4fe067338ccbe05f1acfc142f3700c1736c745b7b06e1cd70afc3f0ee66128`
- Exact head archive SHA-256:
  `1d6f5cae6f99615d761c580035e4bd9bfcef9fad99f5465d5fc29405f4677fe7`
- Canonical forced-add tree: `fa64310667f4c1849399eedea2e4e05c57936453`
- Runtime Git: one synthetic commit, branch `benchmark-base`, no remote

## Official runtime donor

- Image: `vllm/vllm-openai:v0.17.0`
- Linux/amd64 manifest digest:
  `sha256:14ea8b431aaaf75eb873c46c8ebfbad2b4b0790d30c66126d789d8cb9bd0aab9`
- Runtime: Torch `2.10.0+cu129`, CUDA `12.9`
- Exact Git packages: `git=1:2.34.1-1ubuntu1.17`,
  `git-man=1:2.34.1-1ubuntu1.17`, `liberror-perl=0.17029-1`

The exact base declares Torch 2.10.0, but the nearest pre-cutoff official
release (`v0.15.1`) uses Torch 2.9.1. `v0.17.0` is the first official
ABI-compatible donor and was published 18 days after the base cutoff. The
image therefore copies exact base Python/Triton source and only the eight
native files plus two generated flash-attention import shims listed in
`native-donor.json`. None intersects the five PR target files. This scoped
post-cutoff donor risk is intentional, explicit, and machine-checkable.

## Runtime scope

The hidden verifier is a focused, single-GPU execution of the real production
Triton slot-mapping kernel with DCP world/rank metadata. It prepares local
sequence metadata outside graph capture, then captures and replays the
production slot-mapping kernel over persistent buffers using a real CUDA
graph. It does not load a model or initialize a multi-rank NCCL process group.

Full acceptance still requires four GPUs, `DeepSeek-V2-lite`, TP4/DCP4,
model-runner-v2, end-to-end accuracy, and paired performance. There are no
external source dependencies beyond the pinned official runtime image.
