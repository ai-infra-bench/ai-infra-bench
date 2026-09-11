# Independent challenge

The challenge calls the rebuilt native `torch.ops._moe_C.moe_permute`. It derives the mapping, expert windows and payload invariants on token counts 7, 63, 129, 257, 1000 and 3000 with routing `(23*token + 11*slot + 3) mod experts`, in both alignment modes. Two additional cases use 2049 experts, eleven tokens, hidden width 128 and top-k three. Timing keeps the published 512/4096 workload and 20 warmups, five trials and 50 iterations per trial.

Run `run_challenge.py` after the verifier's unprivileged rebuild and root-owned native staging. The wrapper checks the staged SHA-256, fourteen correctness cases, the scaling stage and complete child output. Oracle and the CUDA-scaling alternative must pass; Base must fail the scaling gate, while the expert-count-cap control must reject the fresh legal expert count. Current commands, outcomes and hashes are recorded in `../e2e-evidence.json`.

The challenge is curator-side and is not copied into the agent image. Timed-size specialization remains a diagnostic outside the published performance workload; it is not an expected-failure control.
