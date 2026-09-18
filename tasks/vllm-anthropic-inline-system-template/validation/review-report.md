# Review and validation: inline-system compatibility (0.0.2)

Retain the task. The approved instruction now names the cross-template placement
scope and preserves other supported layouts for default and explicit templates.
The Oracle and verifier have been hardened and validated on the unchanged image.

## Task statement and semantic boundary

The Qwen3.6 report is a valid reproduction of an inline system message rejected
by its system-first template. The behavior under review is:

Anthropic request -> actual configured template/tokenizer -> rendered generation
prompt -> successful Messages stream/response and correct token-count response.

The CPU model with dummy weights substitutes only the forward computation. The
real vLLM HTTP serving, configured templates, tokenizer, and usage accounting run.
No claim about Qwen answer quality or GPU inference accuracy is made.

## Environment

Base: `16908e132e10f75af93049e865130f8987573f5d`.
Image: `sha256:55238ec6540513e7823ab1574281a7c078b9a0db7535633705ee9cff5f1860aa`.
The image and metadata-only Qwen assets were not changed or rebuilt. Repository
image checks pass. Task-owned verifier, controls and evidence remain outside the
agent image. The user-configured 64800-second agent budget is retained.

## Oracle and alternative

The Oracle adapts rejected text-only inline system messages at the HF renderer
boundary, using the actual resolved template, runtime globals and request options.
It handles both string and normalized text-block representations. Already accepted
conversations remain on their original path; non-text system content is not silently
discarded during retry. It does not branch on model names, sentinel values or a
particular error message.

The independent alternative performs adaptation at the Anthropic API render
boundary instead. Both pass all 44 required SDK operations and the separate
three-operation challenge with a Chinese error, adjacent system turns, Unicode,
text blocks and a normal HF template helper.

## Verifier coverage

There are six template configurations, 18 cases and 44 SDK operations. These cover
Qwen default/explicit templates, another system-first template with different error
wording, permissive default/explicit templates, and ordinary HF runtime context.
Every count response must agree with real non-streaming generation usage and,
where exercised, streaming usage. Preserved-layout cases also have an independent
HF tokenizer reference; joining separators in strict templates are not constrained
to the Oracle's representation.

The grader requires exact case/operation inventories, completed modes and terminal
stream events. It evaluates every mode even after an earlier failure. The `ok`
field in a raw SDK operation records HTTP/schema success; a count equality failure
can still make the overall reward zero. `check-summary.sdk_operations` counts
fully validated modes, while e2e-evidence separately records all executed operations.

## Executed Harbor matrix

All entries below are final Harbor 0.22.0 results, with no Harbor exceptions.

| Case | Expected reward | Observed reward | Recorded SDK operations |
|---|---:|---:|---:|
| alternative-retry-on-template-rejection | 1 | 1 | 44 |
| base | 0 | 0 | 44 |
| insufficient-detection-only | 0 | 0 | 44 |
| legacy-template-probe | 0 | 0 | 44 |
| oracle | 1 | 1 | 44 |
| oracle-always-merge | 0 | 0 | 44 |
| oracle-constant-accounting | 0 | 0 | 44 |
| oracle-corrupt-conversation-content | 0 | 0 | 44 |
| oracle-counts-one | 0 | 0 | 44 |
| oracle-drop-inline | 0 | 0 | 44 |
| oracle-duplicate-system-content | 0 | 0 | 44 |
| oracle-messages-only | 0 | 0 | 44 |
| oracle-narrow-error | 0 | 0 | 44 |
| oracle-os-exit-zero | 0 | 0 | 44 |
| oracle-systemexit-zero | 0 | 0 | 44 |


The SystemExit(0) and os._exit(0) controls reach the real count endpoint after
startup. Passive process observers recorded actual zero exit status from the
server process; the required HTTP checks fail and both final rewards are zero.
The observer does not modify the frozen candidate or verifier code.

Constant count and jointly forged count/usage controls complete HTTP operations
but fail numerical validation. The old Oracle and deliberately incomplete or
corrupt repairs also receive zero. Detailed results, hashes, logs and the final
Oracle job/trial identifiers are recorded in `e2e-evidence.json`.

## State and limitations

The same final Oracle and alternative also passed full Docker grading before the
Harbor runs, providing two complete executions of each positive implementation.
This is a bounded behavioral and early-exit validation, not an exhaustive proof
against arbitrary modifications outside the task worktree or installed libraries.
The original 0.0.1 evidence and historical model rewards are preserved. Validation was performed on local, uncommitted changes; no image publication,
push or PR was performed during validation.
