# vLLM multimodal merge memory

Repair multimodal embedding merge resource usage while retaining ordered, in-place output and useful count errors. The contract is in [instruction.md](instruction.md).

The environment is an offline, exact-Base vLLM checkout with PyTorch CUDA, pinned local pytest tooling, a non-root agent and a 10-hour budget. It requests one A100 GPU, 8 CPUs, 16 GiB RAM, and 50 GiB storage. Model weights are not required for this Python/PyTorch boundary.

The shared verifier runs in the agent's container with a 7200-second Harbor budget. It measures both mask devices, checks CPU-mask synchronization, exercises nested/tensor inputs and existing CUDA-mask OOV preparation, and rejects singleton/zero count mismatches. Consecutive calls also change placeholder positions, source values and text embeddings while reusing equal-sized buffers. A root supervisor requires authenticated ordered checkpoints emitted by the preloaded test suite after privilege drop. Stdout success strings never establish completion. These checks cover specific Python-level bypasses; they do not establish a sandbox against arbitrary native-code attacks.

- `environment/`: pinned source/runtime construction and offline test-tool wheels.
- `solution/`: corrected Oracle; hidden from the evaluated agent.
- `tests/`: scorer, behavioral cases and native checkpoint authenticator.
- `validation/`: the case manifest, current control patches, and reusable maintenance tools.

Run with a Harbor provider that provisions the declared GPU:

```bash
harbor run -p tasks/vllm-multimodal-merge-memory -a oracle --cpus limit --memory limit --env <gpu-provider>
harbor run -p tasks/vllm-multimodal-merge-memory -a nop --cpus limit --memory limit --env <gpu-provider>
```

Use a provider that honors the GPU declaration; the repository's leased Docker backend is described in [GPU runner instructions](../../.github/GPU-RUNNERS.md). Keep measured results with the corresponding CI or Harbor run records. Earlier rollout reviews and version-specific results remain in Git history and apply only to their recorded snapshots.
