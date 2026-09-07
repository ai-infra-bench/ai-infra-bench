# Validation record

> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.

Validated on 2026-09-04 with the account-local Docker daemon at
`/root/workspace/dxz-workspace/.docker-dxz/run/docker.sock` and an NVIDIA
H20-3e. Runtime networking was disabled.

## Locked environment

- Base commit: `be3af2d29e2507f32b2190fe015cd6609b348caa`
- Oracle commit: `ab33d2a629be6eca2dd946b1628af4d23d39c547`
- Canonical base tree: `fa64310667f4c1849399eedea2e4e05c57936453`
- Solution SHA-256:
  `10fccf7b1cffcdbb62b57984e164a11de7199108e60ee5ee4729ea7b61f0dcce`
- Review image:
  `sha256:7792b42889e75404a2561c36d00b92acba33c66f5efffdabe33aa7dc5a8d9e8c`

The image runs as `agent`, has one writable synthetic commit and no remote,
and contains no hidden tests, solution, public reproduction, or `agent-test`.
The previous weak-mode script was removed because it contradicted the hardest
instruction's request that the Agent construct its own focused tests.

The nearest same-ABI official runtime is used only as a native donor. The
copied artifacts and two required Python shims are enumerated and hash-locked;
none overlaps the PR's changed files.

## Behavioural controls

| Candidate | Expected | Observed | Reason |
|---|---:|---:|---|
| Locked Base | 0 | 0 | Production V2 block tables have no DCP layout input and cannot produce rank-local slots. |
| Accepted Oracle | 1 | 1 | Capacity, slots, replay, and graph metadata pass. |
| Early incomplete Opus patch | 0 | 0 | It does not expose a complete configured DCP layout to production block tables. |
| Later slot-only Opus patch | 0 | 0 | It fixes rank-local slots but omits DCP-local sequence lengths from CUDA-graph attention metadata. |
| Private-helper-renamed Oracle | 1 | 1 | Renaming the local-length helper and all production consumers does not affect behavioral grading. |

The hidden verifier uses the Base-existing production `BlockTables`,
`append_block_ids`, `compute_slot_mappings`, and graph-input preparation paths.
It discovers configuration parameters by semantic role rather than requiring
the Oracle's private helper names. It covers:

1. non-DCP and DCP sizes 2/4, ranks 0/1/3, and interleave sizes 1/2;
2. two requests, two cache groups, different block sizes, and DCP-scaled table
   capacity;
3. rank ownership, local offsets, padding slots, and ordered block mapping;
4. mutation of persistent position buffers followed by real CUDA graph replay;
5. propagation of DCP-local sequence lengths into attention metadata during
   CUDA-graph warm-up.

This is a rank-local production CUDA reduction on one GPU. It does not claim
NCCL collective behavior, TP4/DCP4 process topology, model-level accuracy, or
throughput. Those remain external release gates rather than hidden benchmark
requirements.

## Fresh hardest-mode Agent run

The first Opus-5 attempt ended after repeated model-gateway timeouts. It made no
change, so it is retained as infrastructure evidence and excluded from Agent
accuracy.

The retry ran for 2,063 seconds and 100 Agent turns, reaching the configured
`$12` budget. It inspected the V1 and V2 runners, DCP configuration, attention
backends, KV-cache coordinator, CUDA-graph input preparation, GPU-worker
selection, and speculative path without seeing a public reproduction. It then
began a production change in `vllm/v1/worker/gpu/block_table.py`, adding CP
constructor state and changing table capacity, but budget exhaustion interrupted
the next edit before slot mapping, call-site wiring, and graph attention metadata
were implemented.

The frozen 2,214-byte patch scores `0`: the verifier reports
`DCP block-table width is wrong: 16!=8`. This is an expected incomplete-Agent
failure, not verifier infrastructure failure. The trajectory is stored under
`ai-infra-bench-data/opus-5-gpu-v3-hard/vllm-pr-34179`; the excluded timeout
attempt is preserved beside it as `vllm-pr-34179-infra-timeout-round1`.
> **Historical evidence only.** The instruction, verifier, task configuration,
> or environment changed during the current hardening pass. These results do
> not validate the current executable snapshot and must be regenerated.
