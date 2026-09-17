# vLLM multimodal merge memory

Repair multimodal embedding merge resource usage while retaining ordered, in-place output and useful count errors. The contract is in [instruction.md](instruction.md).

The environment is an offline, exact-Base vLLM checkout with PyTorch CUDA, pinned local pytest tooling, a non-root agent and a 10-hour budget. It requests one A100 GPU, 4 CPUs and 16 GiB RAM. Model weights are not required for this Python/PyTorch boundary.

The separate verifier runs 26 behavioral cases. It measures both mask devices, checks CPU-mask synchronization, exercises nested/tensor inputs and OOV preparation, and rejects singleton/zero count mismatches. A root supervisor requires authenticated ordered checkpoints emitted by the preloaded test suite after privilege drop. Stdout success strings never establish completion. The bounded threat model and exact behavior map are in [validation/semantic-boundary.md](validation/semantic-boundary.md).

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
