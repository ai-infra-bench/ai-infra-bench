# Final review — task 1.3.4

The task can be retained. No known substantive task, environment or verifier
blocker remains in the reviewed scope. Executable revision:
`d4ebf3d6b8f68a142e7afa07d828936c02bdda73`.

## Contract and semantic boundary

Media placeholders, masks and prompt windows -> real capacity planning,
scheduler admission and whole-item reservation -> real cache lifecycle and
ordered main/lookahead embedding selection. Media geometry and encoder output
production may be controlled; accounting, analytical estimates and downstream
consumers execute candidate code. This validates CPU orchestration, not GPU
inference. The fixed image and `/workspace/vllm` environment are unchanged.

## Fairness correction

The public contract does not mandate a positive capacity when the global encoder
output upper bound is zero. Version 1.3.4 accepts either zero or the configured
floor for each scheduler capacity in those cases, requiring the runner budget
to equal their minimum. Nonempty cases remain exact. This does not allow an
empty current request to clear a global capacity needed by other requests.
A new positive control applies an early zero return only when all modality
output upper bounds are zero. Empty-window advancement, empty placeholders,
nonempty capacity planning and real analytical video estimates remain covered.

## Current validation

On A100, using the pinned image, eight actual `test.sh` control runs matched
all expected rewards: Base 0; Oracle 1; zero-output alternative 1; five incorrect
controls 0. Both positive controls also completed independent cache and capacity
challenges. This is a targeted regression run, not a rerun of all historical
27 controls. Matcher probes additionally rejected negative, oversized and
inconsistent empty budgets and zero capacity for a nonempty case.

Four saved Codex gpt-6-astra medium answers were replayed, with no new model
calls: 0/4 rewards, four capacity-challenge failures, three cache-challenge
passes and four clean post-state checks. This result does not by itself imply
that every failure is model capability. The full native Codex trajectories
have not been reviewed; earlier video-failure diagnosis is separate from the
current aggregate replay result.

The final 1.3.4 Harbor CollectionCanary completed 1/1 with mean reward 1.000.
It applies the Oracle and harmless capture markers and makes no model call.
It is distinct from direct Docker validation. Raw run location:
`A100:/tmp/pr84-canary-134-final`.

## Evidence and history

[e2e-evidence.json](e2e-evidence.json) records current executable hashes and
validation scope. [rollout-review.md](rollout-review.md) and its hashed evidence
archive document the 1.3.3 flash campaign and full controls. Those historical
runs are not relabeled as 1.3.4 results. The old 1.3.0 final report and evidence
are preserved under `history/1.3.0-before-final-evidence-*`.

This update changes only evidence and review documentation. Instruction,
Oracle, image, verifier and controls remain at the tested executable revision.

Strict evidence audit passed with 4 checks, 0 errors and 0 warnings, including
the repository task validator. Seven historical successful verifier captures
were renamed from `.json` to `.log` because they contain a trailing PASS marker;
their raw bytes and SHA-256 values were preserved.
