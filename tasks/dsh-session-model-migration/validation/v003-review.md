# Version 0.0.3 hardening

This revision implements the approved first-principles capacity policy and rollout-review findings. Both full references pass 28/28, Base scores 0, all eight negative controls score 0, and Harbor returns Oracle=1, early-exit=0, forged-report=0 with zero errored trials. Compilation and all 116 focused upstream regressions pass. Final records are in `e2e-evidence.json`. Original model artifacts and scores are unchanged.

## Contract changes

The destination context window and maximum output capacity must both be known. Admission reserves a caller allowance, otherwise a destination request default, otherwise maximum output capacity. The reservation must not exceed maximum output capacity, and retained input plus reservation must not exceed the context window. Exact equality is accepted. Caller ownership survives migration and reopen, including an empty session. A capacity reservation is not a request default.

This explicitly adds output-capability enforcement to the earlier ambiguous statement. Historical GPT-6 scores therefore remain observations for version 0.0.2, not results for this policy.

## Behavioral boundary and coverage

Normal provider profile / caller options → real Loader, pi-ai model catalog, LLM runtime, Session Controller, token meter and durable selection → accepted/rejected selection and unchanged events on failure → saved-event reopen → actual loopback HTTP request and executed tool results.

Only external model-generated SSE responses are substituted. Unknown metadata uses the existing adapter interface with absent optional metadata. The concurrency case delays existing adapter resolution without replacing its answer. Positive capacity cases use real profiles and settings updates; no test requires candidate-introduced capacity fields.

| Requirement | Cases |
|---|---|
| Exact context fit and destination repricing | Below-bound rejection, equality acceptance, already-selected recheck, system/tool overhead |
| Output capacity | Caller allowance above known output capability; unknown capability despite known caller allowance |
| Caller ownership | Nonempty reopen; empty reopen at two legal values; known capability without request default |
| Default ownership | Different source/destination defaults; consecutive migrations and reopen; capacity-only reservation leaves request config unset |
| Transaction safety | Queued input, active generation, transient queued-and-cleared input during lookup; rejected session remains usable |
| Replay | Provider/model change, plaintext order, parallel/shared-prefix calls, tool-result pairing, same-route native replay, disabled option |
| Legacy behavior | Unchecked selection remains permissive and persists deployment defaults |

The two old over-prescriptive assertions are removed: rejection messages need nonempty content rather than a particular English word; generated call IDs may retain readable fragments, while original native IDs, opaque contents and signatures cannot be replayed as foreign native state. The independent alternate uses a different request-payload projection.

Admission is about retained work, not future prompts. Exact-fit tests increase the context window before a new continuation prompt. The SDK may derive an ordinary wire-level output budget; absence of a Harness request default is checked in the durable request config.

## Reference and checks

Both complete reference implementations now expose model capacity separately from request defaults and persist caller allowances in durable selections before a request header exists. The reference includes source integration regressions and updated types and bilingual documentation.

The generic optional audit helper assumes a repository-name task prefix, a Python requirements output, and `solution/oracle.patch`. This task instead uses its approved `dsh-` slug, Base's pnpm lock and `solution/feature.patch`. Its structural errors are not benchmark defects. Repository validation and a task-specific complete executable-hash check provide the applicable mechanical checks; the unmodified helper output is retained. Full upstream lint, generated docs and live provider API tests are outside this scoped change.

The frozen acceptance snapshot precedes this evidence write. Documentation/evidence checksums may differ afterward; executable hashes and pre/post checks identify the bytes that ran. All changes remain uncommitted.

Saved version 0.0.2 answers score Sol 23/28 and GPT-6 25/28 under version 0.0.3. Both remain reward 0; these are regrades under a changed contract, not new model attempts.
