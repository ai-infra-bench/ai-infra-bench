# Review report

Version 2.1.1 addresses the independent review finding that a correct keyword-only input class was rejected when optional metadata preceded its prompt. The task is not yet ready for publication: multi-token streaming coverage, public text-output verification, and the documented native ABI cutoff approximation remain open.

The driver constructs chunks from the declared public input type and binds the prompt by its public parameter, or the sole required parameter when named differently. Optional metadata retains its defaults. Keyword-only and positional-only signatures are supported without assuming that the first parameter contains text. The adapter is isolated from vLLM imports so its constructor behavior can be checked without a GPU.

The new `keyword-only-public-input.patch` changes only the reference input dataclass to use keyword-only fields with optional sampling parameters first. At PR head `44ca003e6049cdc72271e518920931230c5831e8`, the unmodified grading entrypoint rejected it for a missing prompt argument. The failure log, patch and identity are archived in `evidence/input-adapter-before.tar.gz`.

Eight direct adapter tests cover reordered fields, default preservation, positional-only inputs, a renamed input field, raw strings, TypedDict inputs, duck typing and constructor error propagation. The new correct control is part of the ordinary complete grading matrix. The complete grading matrix has 14/14 expected results: Oracle and all four correct alternatives receive 1; Base and eight registered negative controls receive 0. The keyword-only control completes all 15 public behavior scenarios. A fresh Harbor Oracle also receives reward 1 with zero errored trials. Executable hashes match both runs, and the inspected verifier container uses the pinned image, network isolation and one GPU.

The instruction, Oracle, model reference and environment inputs are unchanged. The scorer still uses one-token streaming segments and does not record public output text. Passing the registered controls therefore confirms this adapter repair and preserved tested behavior, not resolution of those independent scoring gaps.

Version 2.1.0 evidence is preserved under `history/2.1.0-before-input-adapter/`; its archived matrix and Harbor run do not certify the new verifier. Current executable identities and validation results belong to `e2e-evidence.json` and `local-regressions.json`.
