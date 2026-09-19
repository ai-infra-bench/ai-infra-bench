# Validation — MoE permutation batch scaling

This directory checks the task's verifier and preserves curator evidence. The normal model grading entrypoint is `../tests/test.sh`; the repository CI uses the control cases below to check that correct implementations pass and incorrect implementations fail.

## Files to keep

| Files | Purpose |
| --- | --- |
| `ci-cases.json` and the nine root `*.patch` files | CI control cases and their expected rewards. `.github/scripts/task_ci.py` requires the manifest, matching patch files and SHA-256 values. |
| `test_performance_scoring.py`, `test_partition_scoring.py`, `test_high_expert_scoring.py` | Twenty-seven CPU checks of timing, partition and high-ID output observations, including valid alternative row ordering. |
| `challenge/`, `curator-tools/` | Independent native checks and environment/baseline reproduction tools. These are curator tools, not agent inputs. |
| `semantic-boundary.md`, `curator-source-audit.md` | Scope of the native behavior checks and frozen Base source provenance. |
| `tests-hardening.md`, `workspace-migration.md` | Current coverage, measured outcomes and remaining environment publication work. |
| `e2e-evidence.json` | Version 1.3.5 executable identities and actual Harbor results for the expanded verifier. |
| `evidence/tests-1.3.4/` | Historical 1.3.4 image, control matrix, timing repeats and Harbor Oracle summary. |
| `evidence/tests-1.3.3-docker/` | Historical 1.3.3 verifier runs for Base, Oracle, an alternative CUDA implementation and two negative controls. |
| `evidence/harbor-deepseek-v4-flash-1.3.3/` | Completed model trial's score, native provenance and runtime identity. |

## Current evidence and limits

Version 1.3.5 adds eight native behavior cases for actual high-ID expert routing, bringing correctness coverage to 40 cases. Tokens reach the final experts and separated nonempty intervals, with duplicates and empty experts between them. The new checks permit different within-expert orderings and do not prescribe unused storage. Timing inputs, protocol and thresholds are unchanged. Current run identities and outcomes are recorded in [e2e-evidence.json](e2e-evidence.json).

Version 1.3.4 had 32 correctness cases and excluded unused payload and unaligned m_indices from the expert-count comparisons. Its eleven Base/Oracle/control outcomes, independent challenges, timing repeats and Harbor Oracle are historical evidence; see [the 1.3.4 summary](evidence/tests-1.3.4/summary.json). They do not certify the eight additional cases.

The recorded 1.3.3 results below predate this verifier change. The 1.3.3 verifier has 32 correctness cases. Docker validation observed rewards 0/1/1/0/0 for Base, Oracle, the CUDA alternative, the FP8 sign-bit defect and the expert-map rejection defect. The DeepSeek Harbor trial passed all 32 correctness cases with reward 1. See [tests-hardening.md](tests-hardening.md) for timings and linked result summaries.

The historical 1.3.3 runs used a locally migrated Base image. Version 1.3.4 has separate acceptance on the rebuilt Dockerfile image, recorded in `evidence/tests-1.3.4/summary.json`. Run identities and hashes describe the measured snapshots; later instruction wording and this directory cleanup do not retroactively change those records. The Harbor input inventory intentionally retains historical paths from the measured snapshot, including files removed during cleanup.

Raw build/correctness/performance logs and per-run stage, staging, scoring and reward files have been removed. Summaries retain the recorded outcomes and hashes; historical log paths and hashes identify the original runs, not files distributed with this task.

## Historical records

Superseded build reports, task 1.3.2 reviews, formatting-only publication logs and earlier snapshots have been removed from this task directory. They are not CI dependencies. Versioned validation summaries remain under `evidence/`; the original historical rewards have not been reclassified.

A local recovery copy is available at `/tmp/pr72-validation-history-archive/`, with original relative paths and SHA-256 values in its index. This temporary backup is not a portable repository artifact or a requirement for running the task. The full directory before cleanup was also backed up to `/tmp/pr72-validation-before-cleanup.tar.gz`.

## Local checks

Run from the repository root:

```sh
python3 .github/scripts/task_ci.py validate vllm-moe-permute-batch-scaling
python3 -m unittest discover -s tasks/vllm-moe-permute-batch-scaling/validation -p 'test_*_scoring.py'
```

The CPU tests check the scorer; they do not substitute for A100 native correctness or performance runs. Keep concise result summaries and reproduction inputs under `evidence/`. Do not add raw run logs, per-stage records or compressed archives to the task directory.
