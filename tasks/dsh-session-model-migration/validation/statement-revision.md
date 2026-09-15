# Statement revision — 2026-09-11

The current instruction is an editorial draft for joint review. It reorganizes the existing migration contract around continuing a session on another model. This is a statement-only review, not a new three-gate task approval. The version remains the development version 0.0.2 pending a frozen candidate.

The prior statement is preserved in [instruction.before.md](../../../artifacts/dsh-migration-statement-rewrite-20260911/instruction.before.md). [The comparison record](../../../artifacts/dsh-migration-statement-rewrite-20260911/comparison.json) records word counts, hashes, and the unchanged task inputs. Historical pass@4, Docker, and Harbor evidence remains attached to its original inputs; it does not measure solver performance on the rewritten statement.

## Editorial decisions

- Keep one user objective: continue existing work on another provider or model. Capacity and gateway history compatibility are the two conditions for that workflow.
- Combine overlapping rejection, persistence, and isolation statements; keep the public options and gateway representation explicit.
- Express exact-fit acceptance as “do not exceed.” Preserve empty-session handling, repeated selection checks, destination token estimates, and caller/default output policy.
- Make output allowance preservation across reopening explicit in the same sentence as caller ownership. This clarifies the existing contract already used by the prior review; it does not excuse the open reference bug.
- Replace the step-by-step testing script with integration coverage of continuation using new calls and results, migration/reopening, and rejection.
- Condense the future-input/provider-availability caveat to “Admission covers the retained work at selection time.” This is a scope statement, not a promise to reserve future capacity or guarantee external service availability.

## Contract cross-check

Paragraph numbers below exclude the title. Case numbers refer to the unchanged ordering in `tests/expected-tests.json`. These are semantic mappings, not a certification of individual assertions.

| Contract | New paragraph | Existing cases |
|---|---|---|
| Opt-in checked selection; existing behavior without the option | 2 | 10 |
| Destination estimate includes retained history, latest system/tools, output; equality allowed; selected route rechecked | 3 | 1 |
| Caller output retained; old adapter defaults replaced | 3 | 2, 3, 21 |
| Empty-session capacity and explicit output; unknown limits rejected | 3 | 4, 5, 6, 19 |
| Idle/no pending input; reject changes during the check | 4 | 7, 8, 9 |
| No generation during checking; useful rejection; original route remains usable; no selection record | 4 | 7, 9, 12 |
| Session-local durable selection; history, results, and provenance retained | 4 | 11, 12, 21 |
| Boolean gateway option, default off; enabling restricted to Responses routes | 5 | 17, 18, 20 |
| Plaintext association/order on provider or model changes; no foreign native state | 5–6 | 13, 14 |
| Correct parallel call/result pairing despite provider-specific IDs | 6 | 11, 22 |
| No fabricated reasoning; native replay and disabled behavior preserved | 6 | 13–17 |
| Continued tool work after migration/reopening and rejected migration | 7 | 11, 12 |

Public types, configuration validation, and documentation remain required in paragraph 7. The prior review's limitation concerning independent type/documentation scoring still applies. The existing 22 cases still miss successful empty-session migration followed by reopening before the first request; the independently reproduced R8 finding remains open.

## Remaining review work

The primary-agent editorial cross-check found no intended removal of a scored behavioral requirement. Joint review should assess whether the capacity paragraph remains too dense and whether the gateway compatibility details are understandable in the user workflow. This does not establish that the current verifier fairly scores every valid implementation.

The three existing P1 findings remain open: R6 error-text matching, R7 whole-payload ID substring matching, and R8 explicit output allowance persistence for an empty session in both reference implementations. No test, reference implementation, environment, or model submission was changed in this revision. Before release, harden those components, freeze the statement and candidate version, and perform the applicable review and validation.
