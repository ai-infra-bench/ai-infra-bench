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
- Runtime Git: exact upstream base and its reachable ancestors, branch
  `benchmark-base`, no remotes, tags, reflogs, or unreachable future objects.

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

Additional behavioral coverage drives the real GPUModelRunner lifecycle and
sampler with a deterministic lightweight model consumer. This is not full
distributed model-serving validation: four-GPU TP4/DCP4, model accuracy, and
paired serving performance remain outside this task's verified scope. Local
calibration uses H20 hardware and does not certify the declared A100 runner.

## Offline testing and donor isolation (task 1.4.1)

`requirements.txt` pins pytest and tblib so the existing upstream worker tests
can run offline as the agent user. Native donor files are copied before the
donor Python package and `/vllm-workspace` are removed. The installed package
path becomes a symlink to the candidate source; curator-only environment lock
metadata is removed from the runtime filesystem. The final scratch stage
copies only this cleaned filesystem, excluding historical donor layers.
Previous images retained another readable donor Python tree; historical runs
are not evidence that this revised isolation was present, nor proof that an
agent actually read the donor tree.
