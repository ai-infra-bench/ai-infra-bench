# Author validation results

> Historical v0.0.2 qualification record. For the current v0.0.3 verifier repair and fresh Harbor matrix, see [verifier-v0.0.3.md](verifier-v0.0.3.md). The original acceptance evidence is retained byte-for-byte in [e2e-evidence-v0.0.2.json](e2e-evidence-v0.0.2.json).

**Retain the task: local qualification passes for v0.0.2. Registry image
publication remains pending.** All ten dimensions below are assessed (19/20);
there are no local qualification blockers. The publication gap is unchanged.
The prompt and verifier changes were independently reviewed before the formal
runs. Results below certify this revision, not earlier instruction wording.

| # | Dimension | Score | Evidence or limitation | Next action |
| --- | --- | --- | --- | --- |
| 1 | Realistic and clear request | 2 | First-person review-and-approve workflow, concrete interfaces and normal-resume scope; independent statement review | None |
| 2 | Independent of a source PR | 2 | The user workflow defines correctness; no repair, storage schema or source-PR guidance in the prompt | None |
| 3 | Solvable environment | 2 | Unchanged pinned Base/image; normal public extension APIs, offline dependencies, CPU resources and 10-hour agent budget; formal correct controls pass | Retain immutable image identity |
| 4 | Statement/test alignment | 2 | All 18 contract and 4 lifecycle scenarios retained; required state fields checked without synthetic defaults; representation freedoms exercised | See diagnostic-language limitation below |
| 5 | Real semantic execution | 2 | Real loader, input path, tool dispatcher, scheduling, file effects and separate-process session resume; only model responses and human choices scripted | None |
| 6 | Correct implementation diversity | 2 | Independent event-journal implementation and separate public-output variant both pass | None |
| 7 | Wrong implementations rejected | 2 | Base and all ten unchanged negative controls receive 0 for their intended omissions | None |
| 8 | Oracle independently challenged | 2 | Independent statement/diff review; previously independently derived normal-resume challenge retained as L04; Oracle and alternative pass current lifecycle checks | None |
| 9 | Trustworthy scoring | 2 | Worker permission checks, independent exact inventories, six integrity checks and real early-exit rejection; limited to documented isolation boundary | None |
| 10 | Reproducible acceptance and handoff | 1 | Final Harbor results and file hashes retained; local immutable image available, registry publication pending | Validate and publish an immutable registry reference |

## Statement and verifier review

The statement was rewritten before verifier changes, then independently reviewed
without consulting the solution. It is 669 words, down from 1,150. It describes
what the user wants to review, approve and resume, without an implementation
sequence, private persistence format, fixed error vocabulary or test hints.
The final review clarified that `plan_submit` is available only while planning;
this preserves the existing behavior requirement.

The five required public state fields remain `sessionId`, `mode`, `planId`,
`revision` and `steps`. The redundant `approvedRevision`, fixed normal-state
sentinels, revision origin/step size, success `errorCode: null`, and simultaneous
JSON-text/details duplication are no longer required. Revisions must still
increase for every accepted submission, including identical text. One actual
structured result channel must match current status. Extra fields cannot affect
plan-state equality. The observer validates actual fields before projecting
them; it never fills in missing values.

No behavior case or regression requirement was removed. Rejection checks also
verify unchanged tools and provider-request counts. Exact session/plan/revision
approval, delayed UI approval, source restrictions, busy/pending inputs, direct
disabled-tool calls, exact tool restoration, actual approved model input,
one-time execution, progress display and cross-process resume remain required.

Rejection diagnostics have a deliberately limited machine check: an extra
nonblank string is a diagnostic candidate, but its natural-language usefulness
is not judged. Unrelated metadata could satisfy that check. The verifier does
not use that string as evidence of safe rejection: state, tools, requests and
side effects are observed independently. Imposing a hidden field-name whitelist
would reintroduce an unjustified output-format constraint.

Gate 1 (statement), Gate 2 (environment) and Gate 3 (verification) pass within
the documented local scope. The semantic boundary is user input or a model tool
call -> real Pi extension, approval, dispatcher, scheduling and persistence ->
approved model input, file effects, tool selection and cross-process resume.
Faux model output and scripted UI selections supply inputs only. The unchanged
image inputs and reference implementations retain their earlier cutoff and
visibility review; this revision did not rebuild the image or add task-specific files to it. The task tests and controls remain outside the agent image.

## Formal validation

The fresh 14-case matrix completed through Harbor 0.23.0 on
`sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`.
Each case completed one trial with zero errored trials and the expected reward.
The standard repository preparer applied every patch directly to pinned Base.

| Case | Reward | Required behavior failures | Known original Base assertion observed |
| --- | ---: | --- | --- |
| `base` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | No |
| `oracle` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `alternative-event-journal` | 1 | None (18 contract + 4 lifecycle passed) | No |
| `minimal-public-state` | 1 | None (18 contract + 4 lifecycle passed) | Yes, exact pinned signature |
| `accept-stale-revision` | 0 | C06, C15 | No |
| `accept-extension-control` | 0 | C07 | No |
| `replay-duplicate-approval` | 0 | C10, C16 | No |
| `allow-custom-planning-tools` | 0 | C02, C09, L01 | No |
| `replay-approved-resume` | 0 | L02 | Yes, exact pinned signature |
| `resume-original-toolset` | 0 | L01 | No |
| `drop-approved-request-context` | 0 | C10, C16 | No |
| `early-exit-zero` | 0 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | No |
| `drop-done-progress` | 0 | C12 | Yes, exact pinned signature |
| `drop-ui-approved-request-context` | 0 | C16 | No |

All runs retained the complete 2,154-case regression inventory and 50 original
skips, with no unaccepted regressions. Oracle and the event-journal alternative
each passed 2,104 cases without an exception. The public-output variant had one
raw failure: the pinned AuthStorage assertion, matching the exact signature on
all three reported attempts. Its regression gate passes under the unchanged
conditional policy. All observed exceptions are recorded above; unrelated
failures and changed skips are rejected.

`minimal-public-state` is an Oracle-derived representation control, not a second
algorithm. Its public state omits `approvedRevision`, adds a changing diagnostic
field, provides successful submission state only in details, and reports free
text reasons without `errorCode`. Its private state transitions, tool policy,
scheduling and persistence are unchanged. `alternative-event-journal` remains
the materially different algorithm. All ten negative-control patches are
byte-for-byte unchanged from the preceding revision.

The early-exit control still reaches extension loading: Vitest catches
`process.exit(0)` and the lifecycle child terminates without its required state
payload. Neither is accepted as completed verification. Six scoring-integrity
self-tests also pass. A final standalone Harbor Oracle run on the same frozen
runtime returned 1 with zero errored trials; its input and raw-artifact hashes
are recorded in `e2e-evidence.json`.

## Saved candidate replays

Four unchanged source archives were restored, checked by file hash and graded
through Harbor. No new model calls were made and no model solved the new prompt.
The results agree with their earlier grades:

| Retained candidate | Reward | Required behavior failures |
| --- | ---: | --- |
| `codex-gpt55` | 0 | C04, C17, L04 |
| `codex-astra-max` | 1 | None |
| `traex-astra` | 1 | None |
| `traex-gpt55` | 0 | C04, C05, L04 |

See `candidate-rechecks.json` for original configurations, source archive hashes,
restoration checks and current verifier results. These are compatibility checks,
not a new difficulty estimate, success-rate measurement or model ranking.

## Evidence and remaining limits

`e2e-evidence.json` hashes the final reviewable task files and the unmodified raw
Harbor artifacts. Evidence-only documentation is written after execution; the
record separately binds the executed instruction, verifier, solution and image.
`initial-matrix-evidence.json` remains explicitly historical and does not certify
this revision. The historical observer probe and original AuthStorage
reproduction are unchanged; their scope is described in `behavior-map.md` and
`baseline-environment.md`.

No shared templates, skill scripts, environment inputs,
Oracle, scoring wrappers or regression policy were changed. Public image delivery
still requires the repository workflow to validate the actual registry image.
The documented same-worker assertion-tampering and non-snapshot OS build limits
also remain. Crash recovery and in-flight shutdown are outside the task.
