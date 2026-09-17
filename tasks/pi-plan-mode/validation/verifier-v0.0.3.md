# Verifier correction and validation: v0.0.3

The v0.0.3 verifier repairs five fixture/observer defects found in completed
v0.0.2 rollouts. It keeps the same statement, Base, image, reference solutions,
12 declared CI cases, 18 contract checks, 4 lifecycle checks, six integrity
self-tests, and 2,154-case regression inventory. No new model rollout was run.

## Contract basis and changes

| Finding | Contract/API basis | Correction and preserved observation |
| --- | --- | --- |
| F1: wrong extension mode | Pinned `ExtensionMode` and real interactive host use `tui`; `interactive` is an input-source value. | Bind UI fixtures as `tui`; ordinary user input retains source `interactive`. |
| F2: missing normal shutdown | The task requires normal quit/resume; pinned `AgentSessionRuntime.dispose()` emits `session_shutdown` before session disposal. | After abort and idle, emit the public `{type: session_shutdown, reason: quit}` event before disposal. The fixture remains a real AgentSession host, not a full terminal-process driver. |
| F3: C15 asynchronous review and result attribution | A stale selection may validly reopen current review and emit a separate approve rejection. | Supply Stay for later dialogs as they appear; associate enter/status/approve results with the requested operation while requiring exactly one associated result. Unknown-command operation naming remains unrestricted. State, tools and approval effects must still remain unchanged. |
| F4: C17 imposed repeated review | The task requires actions after an explicit submitted draft, not a repeated popup after unrelated prose. | Independently select Stay and Refine on fresh submitted drafts. Both preserve draft/restrictions and emit no approval; Refine must actually reach model input. |
| F5: structured-state wrapper rejected | The task specifies structured state fields, not a root-only storage shape. | Accept validated fields at the output root or explicit `.state` wrapper in an existing structured channel. Do not supply defaults or ignore missing required fields. |

Only `tests/plan_support.mjs` and `tests/plan.contract.test.ts` changed executable
verification behavior. The scorer, scope rules, original-regression exception,
candidate implementations and control patches did not change. The earlier
same-content revision probes remain diagnostic evidence; this repair does not
add them as scored cases.

## Fresh complete Harbor matrix

All 17 trials completed in Harbor 0.23.0, with zero errored trials, no trial
retries and their expected rewards. Base and all ten negative controls still
receive 0; Oracle and both positive controls receive 1. Three complete saved
answers were restored and independently scored through Harbor's Oracle path.

| Case | Reward | Contract passed | Lifecycle passed | Failed or missing behavior | Seconds |
| --- | ---: | --- | --- | --- | ---: |
| `base` | 0 | 1/18 | 0/4 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | 134.70 |
| `oracle` | 1 | 18/18 | 4/4 | None | 139.10 |
| `alternative-event-journal` | 1 | 18/18 | 4/4 | None | 141.76 |
| `minimal-public-state` | 1 | 18/18 | 4/4 | None | 147.27 |
| `accept-stale-revision` | 0 | 16/18 | 4/4 | C06, C15 | 146.35 |
| `accept-extension-control` | 0 | 17/18 | 4/4 | C07 | 147.14 |
| `replay-duplicate-approval` | 0 | 16/18 | 4/4 | C10, C16 | 144.51 |
| `allow-custom-planning-tools` | 0 | 16/18 | 3/4 | C02, C09, L01 | 143.54 |
| `replay-approved-resume` | 0 | 18/18 | 3/4 | L02 | 143.03 |
| `resume-original-toolset` | 0 | 18/18 | 3/4 | L01 | 140.84 |
| `drop-approved-request-context` | 0 | 16/18 | 4/4 | C10, C16 | 141.84 |
| `early-exit-zero` | 0 | 1/18 | 0/4 | C01, C02, C03, C04, C05, C06, C07, C08, C09, C10, C11, C12, C13, C14, C15, C16, C17, L01, L02, L03, L04 | 135.08 |
| `drop-done-progress` | 0 | 17/18 | 4/4 | C12 | 152.52 |
| `drop-ui-approved-request-context` | 0 | 17/18 | 4/4 | C16 | 149.97 |
| `saved-astra-xhigh` | 1 | 18/18 | 4/4 | None | 148.43 |
| `saved-astra-medium` | 1 | 18/18 | 4/4 | None | 140.60 |
| `saved-sol-xhigh` | 0 | 17/18 | 3/4 | C04, L04 | 141.35 |

The matrix elapsed 869.57 seconds with at most three task
trials running concurrently. Every trial passed scope, the full regression gate,
and all six integrity self-tests. Every regression run contained exactly 2,154
cases and 50 original skips. The exact pinned AuthStorage assertion was observed
in: `alternative-event-journal`, `allow-custom-planning-tools`, `drop-approved-request-context`. Raw failures and process
exit codes remain in the evidence.

One unresolved process anomaly is preserved: `drop-done-progress` returned
regression-process exit 1, while its complete JUnit reports 2,154 cases, 50 skips,
zero failures and zero errors. Its 292-line log supplies no causal error; this
is not the pinned AuthStorage exception. The unchanged regression gate accepts
the full JUnit inventory, while C12 independently rejects this negative control,
so its final reward remains 0. No positive run has an unexplained nonzero
regression-process exit: the alternative's exit 1 is accompanied by the exact
pinned AuthStorage assertion; Oracle, minimal-public-state and both Astra
saved answers have regression-process exit 0.
No rerun replaced this evidence. A similar unexplained process exit occurred in
an earlier diagnostic negative-control run; neither observation is attributed
to a cause unsupported by its logs.

The two Astra saved answers now receive 1. Their original v0.0.2 rewards remain
0 and are not rewritten. The Sol xhigh saved answer still receives 0: C04
observes that invalid submission returns a successful tool result (`isError`
false); L04 observes normal state becoming planning when resumed with `--plan`.
These failures persist after the fixture corrections.

## Frozen execution and provenance

The canonical v0.0.3 runtime inputs and all 17 prepared task trees were hashed
before the first trial. Each prepared tree was hashed again after completion;
all bytes matched. The exact canonical config hash, every prepared config hash,
shared runtime hashes and per-case solution hashes are recorded in
[`execution-inputs-v0.0.3.json`](execution-inputs-v0.0.3.json). Evidence/report
hashes generated later are distinct from the pre-run execution hashes.

Author cases use the canonical `pi-agent` Oracle/NOP configuration. Saved-answer
replays override `agent.user` to root only for an Oracle restoration shim that
extracts the full captured source and verifies every file hash before scoring.
It executes no candidate script and makes no model calls. The original scorer
then uses its unchanged root coordinator and UID 65534 test workers; each saved
run's regression, contract and lifecycle logs confirm that worker UID. Full
source archives include both tracked and untracked files; restored source counts
are 1,671 (Astra xhigh), 1,672 (Astra medium), and 1,669 (Sol xhigh).

The retained linux/amd64 image is
`sha256:a68c346850d3b3ec045dd52aaf751e229e888ca365de99ab06a99fe88eeb0cda`.
The image gate matched; no image rebuild was needed. The author launcher only
substitutes the registry of Harbor's identical-digest network probe image. Each
task retains 4 CPUs, 8 GiB RAM and no network. Generic CI's older default Harbor
version was not changed or used for these results.

One orchestration setup invocation failed before trial preparation because the
host's default Python was 3.7 and lacked `tomllib`. Its logs and exit code were
preserved separately; the matrix was then launched with Harbor's Python. That
setup failure started zero trials and has no reward. No scored run was silently
retried or overwritten.

## Evidence and limits

- [`e2e-evidence.json`](e2e-evidence.json): current 14-case author matrix, raw
  artifact hashes and current task-file manifest.
- [`saved-answer-rechecks-v0.0.3.json`](saved-answer-rechecks-v0.0.3.json): three
  complete-source Harbor replays, archive/restore checks, actual rewards and
  verifier summaries.
- [`e2e-evidence-v0.0.2.json`](e2e-evidence-v0.0.2.json) and
  [`author-results.md`](author-results.md): preserved historical qualification.
  The older `candidate-rechecks.json` is also historical, not this regrade.

The local image remains unpublished; future registry publication must validate
the delivered immutable image. This is offline regrading, not evidence of new
model success rates or fresh held-out testing. Existing task boundaries remain:
normal idle quit/resume is covered; crash recovery, active shutdown, fork/tree,
reload and arbitrary shell read-only enforcement are outside the contract.
