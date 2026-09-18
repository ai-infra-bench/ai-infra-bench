# vLLM multimodal merge memory

Repair multimodal embedding merge resource usage while retaining ordered, in-place output and useful count errors. The contract is in [instruction.md](instruction.md).

The environment is an offline, exact-Base vLLM checkout with PyTorch CUDA, pinned local pytest tooling, a non-root agent and a 10-hour budget. It requests one A100 GPU, 4 CPUs and 16 GiB RAM. Model weights are not required for this Python/PyTorch boundary.

The separate verifier runs 34 behavioral cases. It measures both mask devices, checks CPU-mask synchronization, exercises nested/tensor inputs and existing CUDA-mask OOV preparation, and rejects singleton/zero count mismatches. Consecutive calls also change placeholder positions, source values and text embeddings while reusing equal-sized buffers. A root supervisor requires authenticated ordered checkpoints emitted by the preloaded test suite after privilege drop. Stdout success strings never establish completion. The bounded threat model and exact behavior map are in [validation/semantic-boundary.md](validation/semantic-boundary.md).

- `environment/`: pinned source/runtime construction and offline test-tool wheels.
- `solution/`: corrected Oracle; hidden from the evaluated agent.
- `tests/`: scorer, behavioral cases and native checkpoint authenticator.
- `validation/`: alternative and negative controls, independent challenge, final evidence and historical records.

Run with a Harbor provider that provisions the declared GPU:

```bash
harbor run -p tasks/vllm-multimodal-merge-memory -a oracle
harbor run -p tasks/vllm-multimodal-merge-memory -a nop
```

For the recorded Harbor 0.22 Docker adapter, use `--override-gpus 0`; the task's Compose reservations supply one GPU. Record actual device assignment and provider/version with results. See the evidence index for current acceptance status rather than treating old results as final validation.

Version 1.3.2 adds six empty-container count checks (32 total), based on independently reproduced false positives in flash-r03. Original rewards remain in the rollout evidence.

Version 1.3.3 adds two repeated-call regressions for CPU/CUDA masks (34 total). They assert observable merge behavior without inspecting candidate caches, helpers or algorithms. A stale-placement negative control records the previously accepted defect; see [repeated-call validation](validation/repeated-call-review.md).

The historical A100 flash campaign, score corrections and v1.3.2 validation boundary are in [rollout review](validation/rollout-review.md), with all 16 attempt records and portable evidence.
