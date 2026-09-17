# Config preflight and execution-error follow-up

The verifier now uses a real local `ModelConfig` for config preflight, with the scheduler limit matching the model's 2048-token context. Generic runtime failures are labeled `EXECUTION_ERROR`; they still prevent a passing score, and the label does not assign a cause.

All three original submissions were replayed through `/tests/test.sh` in offline containers, each with two GPUs and the unchanged pinned task image. Every submitted changed or untracked file was transferred with matching SHA-256 hashes. The original artifacts and results were preserved. No agent or API call was involved.

| Submission | Reward | Completed checks and failure |
| --- | --- | --- |
| deepseek-1 | 1 | CPU=True, GPU=True; async_pp2=True, sync_pp2=True, async_pp1=True, sync_pp1=True |
| deepseek-2 | 0 | CPU=True, GPU=True; async_pp2=False, sync_pp2=True, async_pp1=True, sync_pp1=True |
| sol-high-2 | 0 | CPU=True, GPU=False; EXECUTION_ERROR: RPC call to sample_tokens timed out. |

DeepSeek 1 passes both behavior suites and all four real-model modes. DeepSeek 2 now passes config preflight and both behavior suites, but its async PP=2 output is wrong: the first request returns `[22, 101, 125, 39]` instead of `[22, 101, 125, 20]`. Its synchronous PP=2 and both PP=1 modes pass. The second submission's zero reward now follows from an actual output mismatch rather than the missing model config.

Sol High 2 again times out collecting the first basic round's `sample_tokens` result, before E2E. Line 46 of its GPU-stage log records `EXECUTION_ERROR` with detail `RPC call to sample_tokens timed out.`; no `INFRA_ERROR` verdict is emitted. This reproduces the previously diagnosed send/receive timing defect with the neutral label, without changing the submitted code. The full Sol replay takes 416.739 seconds; the DeepSeek replays take 501.851 and 503.038 seconds.

The exact results, output comparisons, commands, executable hashes and source identities are in `e2e-evidence.json`; complete logs and candidate overlays are retained in `evidence/config-preflight-replays.tar.gz`. The preceding full matrix is preserved in `history/v1.4.0-before-config-preflight/`. Its 17 additional control cases retain their original verifier hash and are not claimed as rerun.

The only runtime change is in `tests/verify_async_pp.py`; the task statement, image and reference solution are unchanged. The publication target is PR #75; the Git commit containing this record identifies the submitted revision.

Base receives 0 after passing config preflight and then failing the required scheduler reentry behavior. Direct Oracle receives 1 in 497.9 seconds. Harbor Oracle `task__JAEBdV7` receives 1 with no exception, with verifier time 508.528 seconds. Both Oracle runs pass all four real-model modes. The input checksum is `977c213c7d5c0b2bac45d2b5fb191784f97ef800e22d6a8c3c4e6a6e8a7b0c39`; only evidence files changed after Harbor task preparation. Full logs are in `evidence/config-preflight-publication.tar.gz`.

The final verifier SHA-256 is `6f39afb859f3805cf428cd870f16cccda2393ae9e51ea70004a94a971bd42541`. The task image remains `sha256:cf04408e8aed807333ff1522f952182aa7948f2a32e3caeee79dac9b95911e69`. Remote task CI still requires GitHub environment approval and is separate from these local runs.
