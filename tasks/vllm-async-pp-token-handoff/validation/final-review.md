# Final review

Version 1.4.0 can be retained after the Worker/executor repair. Both unchanged Astra submissions receive 1, all 19 active Base/Oracle/control cases match their expected rewards, and Harbor Oracle receives 1 with no exception. The task statement, reference patch and image are unchanged.

GPU behavior now runs the actual scheduler, mp executor, Worker construction and dispatch, activation transport and model input path. It no longer bypasses a valid Worker-owned token receive. The tests also allow equivalent CPU activation metadata APIs, follow EngineCore's empty-step dispatch, and accept skipped discarded-logit work. Five correct alternatives pass; the 13 negative controls cover missing progress, token/prompt corruption, explicit and implicit waits, wrong final-rank behavior, duplicate collection and the demonstrated scoring bypasses.

The serial control is rejected during the causal prefill gate, before E2E. Its delayed second submission ends in failure cleanup and the existing RPC timeout, so this is a 450.6-second negative case rather than an immediate assertion. The generic remote exception label does not determine attribution; underlying candidate and fixture traces are recorded in local-regressions.json.

The direct Oracle and Harbor verifier take 558.8 and 553.117 seconds. The Astra replays take 552.1 and 555.9 seconds; every original changed file is byte-identical. Correct alternatives take 511.1–562.3 seconds on the shared two GPUs. All 41 CUDA observer checks pass. These are representative contract checks and not a universal malicious-code security boundary.

Harbor trial task__mAoVBAA uses checksum 4152b12a5e59f1f2933d2788e69beeee233e414c75ccb58ddf07b43a0045c1c5 and image sha256:cf04408e8aed807333ff1522f952182aa7948f2a32e3caeee79dac9b95911e69. Source hashes, original rescore records, complete logs, prior defects and superseded probes are preserved in e2e-evidence.json and the worker-boundary archives. Runtime files match the tested snapshot; evidence-only updates follow validation.

Strict artifact and staged scope audits pass with no warnings or errors. The validated changes are prepared for the authorized commit and push to codex/async-pp-behavior-hardening; only this task is staged.
