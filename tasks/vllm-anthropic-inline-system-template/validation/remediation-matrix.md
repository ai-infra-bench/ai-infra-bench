# Inline system compatibility hardening (task 0.0.2)

The approved contract uses Qwen3.6 as the reported failure and preserves other
already-supported layouts across tokenizer-default and explicit templates.
The agent budget remains 64800 seconds, as explicitly configured by the user.
The image, source Base and pinned runtime assets are unchanged.

| Finding | Change | Validation |
|---|---|---|
| Scope did not explicitly include other placement rules and template sources | Apply the user-approved concise final instruction paragraph; version 0.0.2 | Instruction diff reviewed by user |
| Oracle treated a missing explicit template as a strict template | Resolve and render through the real tokenizer first; adapt only rejected text-only inline system conversations | Default and explicit Qwen/permissive modes |
| Oracle used an incomplete Jinja context and interpreted unrelated probe failures as placement constraints | Remove the synthetic probe; use the existing runtime and a guarded render retry | Standard HF `strftime_now` template plus independent Chinese-error/adjacent-system challenge |
| A successful count endpoint could always return 1 | Require equality with real generation usage for all cases; independently tokenize preserved-layout cases | Constant-count and jointly forged count/usage negative controls |
| Later modes were absent after an earlier mode failed | Execute all six modes and validate their complete manifests independently | Base and incorrect controls retain per-mode failure records |
| Success exits could be mistaken for completed checks | Require all mode/case/operation records, exact counts, and terminal stream events | SystemExit(0) and os._exit(0) inside the count endpoint, through Harbor |
| Positive calibration depended on one repair location | Keep an independent implementation at the Anthropic API render boundary | Same 44 operations and separate 3-operation challenge |

Raw Docker/Harbor records and final outcomes are linked from `e2e-evidence.json`.
Historical 0.0.1 evidence is retained in `history/0.0.1-evidence.json`; it does not
certify the changed executable files. Historical model-attempt rewards are not
rewritten.
