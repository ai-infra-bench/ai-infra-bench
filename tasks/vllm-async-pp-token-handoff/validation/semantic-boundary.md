# Semantic boundary — vllm-async-pp-token-handoff

sampled GPU token IDs -> real two-process NCCL and production sampling/bookkeeping/output lifecycle -> retained/discarded mappings, cached state, next GPU input and following scheduler round

## Components executed for real

- Two separate processes and two A100 devices with actual NCCL
- Production GroupCoordinator tensor API
- GPUModelRunner constructor, sample_tokens, and production buffers/InputBatch/CachedRequestState
- Real async output consumption, _update_states and _prepare_input_ids
- Production VllmConfig and AsyncScheduler

## Allowed substitutions and their limits

- Deterministic GPU sampling results replace model execution; values do not determine transport, ordering or lifecycle semantics.
- A supervisor launches separate ranks with the same rendezvous/rank environment instead of using torchrun as the grading launcher. Actual distributed membership and NCCL remain real; torchrun is available to the solver.
- A local OPT configuration supports production runner and scheduler construction; no model weights or tokenization are needed for the handoff.

For performance tasks, workload dimensions that influence latency remain fixed
to the public timing contract. A different valid correctness input does not
establish performance equivalence. Fresh independent cases exercise the same
production boundary; they do not replace the production implementation.

## Coverage

- Configuration admits asynchronous PP=2.
- Single and three-request scheduler re-entry with outstanding placeholders.
- Three real NCCL scenarios: basic retained/discarded rows, reordered requests and integrated scheduler-to-next-input consumption.
- Both ranks must finish; sender output materialization, receiver mapping, exactly one retained placeholder and no discarded append are checked.
- Independent five-request challenge has interleaved discards, reordered IDs, nonempty histories and fresh token IDs.
- Object-collective rejection, Python early exits and failure after broadcast; all available phase results remain reported.

Fresh five-request inputs and independently derived expected retained/discarded state; real downstream GPU input consumption remains required.

## Cutoff and provenance

Exact Base and clean retained history. Torch/CUDA/NCCL and the pre-cutoff official vLLM native donor are pinned. Actual candidate import uses /workspace/repo; model configuration is verifier-only and no task fixture enters the image.

See `e2e-evidence.json` for actual run identities and `final-review.md` for the
current review outcome. Earlier build notes are historical observations.

The constructor is semantic: no object.__new__ or hand-filled candidate-private state is used. Production distributed initialization establishes world/TP/PP groups. Constructor-owned transport and receive buffers are exercised by an additional correct alternative. Scheduler reentry means two schedule() calls before update_from_output() while requests remain runnable and resources suffice.
