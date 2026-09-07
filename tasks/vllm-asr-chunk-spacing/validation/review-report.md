# ASR chunk-spacing hardening, task version 0.0.2

Retain the task with the approved inferred-language scope. The Oracle,
independent alternative and verifier now cover the approved changes; all final
Harbor controls behave as expected. These changes are local and uncommitted.

## Contract and semantic boundary

The instruction replaces only its Chinese/Japanese sentence with:

> Do not add boundary spaces to Chinese or Japanese output, even when `language` is omitted.

The existing English boundary examples, both response modes, translation,
model-provided whitespace and clean-chunk scope remain. The statement does not
prescribe a classifier, helper, error path or verifier implementation.

WAV input -> real decoding and audio splitting -> independent chunk output
-> real speech serving aggregation -> JSON/SSE text and stream completion.

The generator and prompt renderer are substituted at normal interfaces; they
do not decide missing text separators. Real Qwen output cleanup and language
validation run for the structured Qwen cases. Full ASR weights, GPU inference,
the Cohere audio frontend and an HTTP server are not claimed to run. The image
still lacks librosa for importing that full Cohere frontend, which does not
determine the clean-text join contract exercised here. All tests, controls and
curator evidence remain outside the agent image.

## Oracle and independent alternative

The Oracle changes only the shared speech_to_text.py response aggregation path.
It selects the output language, preserves supplied boundary whitespace, and
keeps separators between audio chunks rather than token deltas. With an omitted
language it uses Unicode script evidence from the previous non-empty chunk and
the next chunk's first character. Retaining the previous whole chunk handles
CJK text ending in quotes or digits, while using only the next first character
keeps the decision independent of current-delta grouping. Supplementary Han
and halfwidth Katakana are recognized. Empty chunks do not erase prior state.

The alternative wraps each result generator before the original SSE generator
runs, instead of editing SSE emission. It uses a regex script classifier and
retains each original chunk's text for the next boundary. Both implementations
preserve normal English spaces before/after quoted sentences. They do not use
the attempted solution's broad rule that all punctuation suppresses a space.

## Coverage and completion integrity

The 48 regression cases comprise 24 original cases, 8 English quoted-boundary
cases (two shapes x transcription/translation x streaming/non-streaming), 10
inferred CJK clean-output cases, and 6 structured Qwen cases with language
omitted. The latter cover English/Chinese/Japanese and transcription/translation;
Chinese/Japanese translations explicitly select their target language. This
does not assert that an English-target translation should output Chinese.

The required speech pipeline is recorded as one pytest case containing its
three real WAV/split/serving scenarios. A trusted, candidate-free checker requires
the exact testcase-name inventory, unique entries, correct totals and zero
failures, errors or skips independently for each suite. JUnit class labels are
not semantic and depend on invocation paths, so they are not used as a contract.
Stale result files are removed before execution. Both suites are checked even
when a preceding process fails. Zero exit status by itself cannot earn reward 1.

The SystemExit(0) and os._exit(0) controls actually reach the standalone required
pipeline's candidate-module import after all 48 regression cases have passed.
Both print REVIEW_EARLY_EXIT_REACHED and exit with status 0; neither creates the
required pipeline JUnit record, and the trusted checker assigns final reward 0.
This closes the demonstrated bypass, rather than merely changing the selector
so the old attack can no longer reach its target.

## Final Harbor results

All 14 runs used Harbor 0.22.0 and the same frozen executable revision. There
were no Harbor exceptions. Oracle ran last after all other controls completed.

| Case | Expected reward | Harbor reward | Regression passed | Required pipeline |
| --- | ---: | ---: | ---: | --- |
| alternative-stream-wrapper | 1 | 1 | 48/48 | 1/1 |
| attempt8-quote-heuristic | 0 | 0 | 38/48 | 1/1 |
| base | 0 | 0 | 26/48 | Rejected |
| legacy-oracle | 0 | 0 | 36/48 | 1/1 |
| oracle-always-space | 0 | 0 | 42/48 | Rejected |
| oracle-drop-first-chunk | 0 | 0 | 22/48 | Rejected |
| oracle-duplicate-existing-whitespace | 0 | 0 | 42/48 | 1/1 |
| oracle-missing-inferred-language | 0 | 0 | 36/48 | 1/1 |
| oracle-nonstream-still-concatenates | 0 | 0 | 36/48 | Rejected |
| oracle-os-exit-zero | 0 | 0 | 48/48 | Rejected |
| oracle-quote-heuristic | 0 | 0 | 40/48 | 1/1 |
| oracle-systemexit-zero | 0 | 0 | 48/48 | Rejected |
| oracle-translation-uses-source-language | 0 | 0 | 44/48 | Rejected |
| oracle | 1 | 1 | 48/48 | 1/1 |

The original attempt-8 patch is retained exactly as a negative control. Its
8 quote-boundary failures plus 2 halfwidth-Katakana failures are now detected.
The legacy Oracle fails 12 inferred-language cases. This task version does not
rewrite the original eight rewards or the historical 136-attempt report.

## Independent challenge, stability and identity

Oracle and alternative each pass a separate 8-case challenge outside the scoring
inventory: supplementary Han, halfwidth Katakana followed by numbers and quotes,
an English quoted clause, and an existing tab, each in both response modes.
Both also passed complete Docker grading before their Harbor runs, giving two
full successful executions of each positive implementation.

Base: a8134aef4e0cac7ffb72b24d89378df09d88f9cc.
Image: sha256:76bc02fe11ca6ac3f196f3daf5e7a99c9ee6037af9865faf33a0f9359b80daa9.
The existing image, locks and task-specific cutoff overrides were retained;
repository image identity/source checks passed. The agent budget is 36000
seconds, matching the project-wide 10-hour policy. Model-tokenizer assets are
not added to the agent image for this text-assembly task.

This is bounded validation of the stated clean-chunk behavior and demonstrated
early-exit paths, not a claim of language identification for arbitrary mixed or
script-free text, full speech-recognition accuracy, or resistance to arbitrary
host/library/reward-file tampering. Final commands, hashes, actual child exit
statuses, JUnit summaries and Harbor IDs are in e2e-evidence.json. Prior 0.0.1
evidence remains under validation/history. No commit, push or image publication
was performed for this ASR change.
