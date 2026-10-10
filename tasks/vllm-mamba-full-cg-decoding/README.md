# vLLM Mamba FULL-CG decoding

Fix incorrect Mamba outputs when FULL-CG resumes requests with existing recurrent state, while preserving fresh prompts, eager execution, ordinary decode and supported speculative decoding. The developer request is in [instruction.md](instruction.md).

The environment contains the exact frozen Base, pinned native dependencies, one A100, no network and a 10-hour agent budget. Oracle patches, tests and curation evidence are outside the agent image.

The separate verifier calls `LLM.generate` on small local Mamba1 and Mamba2 models. It compares generated tokens and full output distributions with private non-speculative eager results from immutable Base source, including graph replay, state reuse after request completion, and accepted-token speculative decoding. A separate protected native observer checks successful CUDA graph calls during inference. Python profiler reports and a successful process exit cannot establish graph execution. The task uses binary scoring.

See [the local validation record](validation/LOCAL-VALIDATION.md) for the tested Harbor entrypoint, actual results, hardware and reproducibility instructions. [The remediation matrix](validation/remediation-matrix.md) maps the statement and review findings to behavior tests. Historical records in `validation/archive/` do not certify the current revision.
