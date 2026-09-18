# Approved remediation

| Finding | Change | Validation |
| --- | --- | --- |
| The v0.0.1 statement showed transient `FileNotFoundError` but the verifier also required recovery from a transient incomplete read | Describe both brief missing and incomplete reads, and distinguish them from persistent invalid configurations | Base 0; Oracle and parser-local alternative 1; FileNotFound-only control 0 |
| Historical eight model failures were scored against the narrower statement | Preserve them as v0.0.1 history and do not reuse them as v0.0.2 model results | Eight unique patches and their shared failure classification recorded in final evidence |
| JUnit integrity checked only counts | Require the exact four expected testcase names and remove stale result files before grading | SystemExit(0) and os._exit(0) controls reach candidate code but receive reward 0 |
| Correct alternative was described but not retained | Add a parser-local retry alternative at a different repair location | Full Docker and Harbor grading reward 1; independent transient-partial-read challenge passes |
| Agent budget exceeded project policy | Set `[agent].timeout_sec` to 36000 | Repository validator and strict artifact audit |
| Validation evidence was stale and incomplete | Preserve v0.0.1 evidence and regenerate complete v0.0.2 hashes and run records | Strict evidence audit on final artifacts |

The environment image is unchanged because no environment input changed. No
historical reward was rewritten. Changes remain local and uncommitted.
