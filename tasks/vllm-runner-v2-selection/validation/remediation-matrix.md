> Runtime results below apply to the original PR #3 snapshot `fba6a6c`.
> The permission/interpreter follow-up has only static validation. Final
> Base/Oracle/control and non-root Harbor collection validation remain pending.

# Review remediation matrix

| ID | Severity | Finding and evidence | Contract impact | Approved | Remediation | Validation | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P0 | Blocking | At `41106b1`, candidate import could call `SystemExit(0)` or `os._exit(0)`; the shell treated the child exit as success and wrote reward 1. | A malicious or accidental early exit could bypass every behavior check. | Yes | `test.sh` no longer derives reward from the candidate-importing process. A root-owned supervisor initializes reward to 0, owns and grades all 17 cases, and launches a separate unprivileged process that returns only a nonce-bound raw observation for each case. Only the supervisor can replace reward with 1. | Old entry reproduced `os._exit(0) -> 1`; fixed direct runs give both attacks 0 with 0/17 accepted observations. Exact-commit Harbor controls are recorded on the PR. | Fixed |
| P1 | Blocking | The verifier required the unset environment accessor itself to equal `None`, rejecting a legacy boolean accessor with presence-aware configuration resolution. It also required forced-V2 rejection during `VllmConfig` construction. | Correct implementations with different internal representation or validation placement could be rejected. | Yes | Unset accessor accepts `None` or legacy `False`; reward is based on real config-to-worker behavior. Forced-V2 rejection may occur anywhere in startup before a usable worker exists. Added Qwen2, pooling, KV-sharing and logits-processor dimensions. | Existing tri-state alternative=1; new boolean-accessor/presence-aware alternative=1; Base=0, Oracle=1, incomplete=0. | Fixed |
| STABILITY | Blocking | Old validation was tied to the pre-review tests. | Old results cannot validate the repaired scoring snapshot. | Yes | Regenerated all affected outcomes after replacing the scoring protocol. | Base=0 (16/17); Oracle=1 (17/17); boolean-accessor alternative=1 (17/17); both early-exit controls=0 (0/17). Exact-commit Harbor results are recorded on the PR. | Fixed |
| IMAGE | Non-blocking | Tests and solution changed, but the environment did not. | A needless rebuild would not strengthen the executable base. | Yes | Reused and re-inspected the retained digest-pinned image, as allowed by the validation playbook for test-only changes. | Canonical image ID remains `sha256:d22ddb74a5d77fe9df2ce4a04b91fa937c83c9b8ed9105e3dec91fa838019189`; task metadata matches. | Complete |

## Frozen behavior contract

- Unset selection: supported dense, unquantized Qwen3 generation starts with V2.
- Automatic fallbacks: other architectures, pooling, KV sharing, and custom
  logits processors remain on V1.
- Explicit overrides: `0` selects V1; `1` selects V2 when compatible.
- Forced incompatibility: explicit V2 must fail clearly before startup yields a
  usable worker; the precise helper, exception subclass, and validation phase
  are not contractual.
- Consumer propagation: the production GPU worker observes the configuration's
  resolved selection.
- E2E boundary: local HF metadata drives real `ModelConfig`, `VllmConfig`, and
  production `GPUWorker.__init__` on a real CUDA device. Model weights and
  inference kernels remain outside this configuration-selection task.
