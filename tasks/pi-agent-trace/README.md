# pi-agent-trace

**Status: staged (`staged-smoke-only`), task version 0.0.6, validated locally
through the Harbor entrypoint.** See `validation/e2e-evidence.json` for the recorded matrix. The
image is the same template build as `pi-background-processes` and
`pi-history-notes` (identical Dockerfile bytes, so the same image id); the CI
x64 runner has not built or published it yet.

Harness revision 3 (2026-09-17): the agent phase runs as the unprivileged `node` user while the verifier runs as root; the installed toolchain is root-owned so candidate code cannot rewrite the runner that produces the verifier's reports, and `tests/test.sh` rejects submissions that change pi source or the build/test toolchain (see the task review under `validation/`); the pass-to-pass check tolerates the pinned environmental failures in the candidate run too. Verifier cases unchanged.

## What the agent does

Adds an OpenTelemetry trace exporter to [pi](https://github.com/earendil-works/pi)
at a pinned commit, as an extension: one span per run, turn, provider request,
tool execution and compaction, written as OTLP/JSON lines
(`ExportTraceServiceRequest` per line) to a file under the session directory,
with GenAI semantic-convention attributes (model, token usage, cache tokens,
finish reasons), run triggers (prompt / wakeup / continuation), error statuses,
and a `pi.session.entry_id` on every span that ties it to the session entry pi
persisted. The file updates live: every span is written once when it starts
and once when it ends, so a reader tailing it sees a 30-second tool the moment
it begins. See [`instruction.md`](instruction.md).

What makes it more than event logging: pi persists a message only after
extensions have seen its `message_end`, so entry ids have to be resolved at
`turn_end`; run triggers need `before_agent_start` and `agent_settled`
bookkeeping; a reloaded runtime gets no `session_start` without host
bindings; and the file must stay append-only and in end-time order across
reloads and processes.

## Real-agent rollouts (grok-4.6, Grok Build OAuth, temperature 0.1; agent timeout multiplier 0.1 through run 9, 0.15 afterwards)

Grok rows are numbered by grok rollout, opus rows by opus rollout; `validation/e2e-evidence.json` `real_agent_rollouts` lists the same runs in chronological order with a `label` equal to the first column here.

| Run | Reward | Layers | Failure attribution |
|---|---|---|---|
| 1 | 0 | P2P pass, lifecycle 1/1, contract 5/6 | judge defect: the verifier compared span times against millisecond `Date.now()` values while the submission uses a sub-millisecond clock (a run ending 5 ns into the next millisecond, a turn start 1 ns after the event timestamp); both assertions now allow sub-millisecond digits and the unmodified submission passes every layer (`alt-grok-run1`) |
| 2 | **1** | all pass | passes on verifier revision 1 as well (millisecond clock) |
| opus 1 (0.0.2) | **1** | all pass | claude-opus-5 via Harbor's claude-code agent on the 0.0.2 instruction (11 contract cases then), 26 min; a second attempt that day hit the Claude session limit and is not counted |
| 3 (0.0.3) | 0 → 1 | contract 12/13, lifecycle 2/2, P2P pass | judge defect: the shutdown case demanded one shared nanosecond timestamp for the three closes; replaced by a window the verifier observes around `runtime.dispose()` (child-first order kept); the unmodified submission then passes (`alt-grok-run3`) |
| 4 (0.0.3) | 0 → 1 | contract 12/13, lifecycle 2/2, P2P pass | same assertion, same fix; passes unmodified (`alt-grok-run4`) |
| 5 (0.0.4) | **1** | all pass | first attempt at the overflow-recovery and sub-agent edges: both implemented correctly |
| 6 (0.0.4) | **1** | all pass | second rollout on 0.0.4, passes unmodified |
| 7 (0.0.5) | void | agent timed out at 3600 s (36000 s x 0.1) mid-refactor | not a verdict: the host proxy node was switched at 12:41Z, the grok CLI logged auth 401 retries from 12:43Z and a network error at 12:57Z (no other run has a 401); the chained rollout 8 then exited at the proxy preflight and was rerun |
| 8 (0.0.5) | 0 | contract 13/15, lifecycle 2/2, P2P pass | two genuine defects, both reproduced from the submission in the task image: concurrent tool end lines were written in pi's persistence order (the 300 ms call before the 100 ms call, `endTimeUnixNano` decreased) because the extension deferred each end line until its tool-result entry existed; and the shutdown path closed `pi.run` with an empty attribute list (no `pi.run.turn_count`, no entry id for the persisted user message). A 54-line curator fix (tool ends flushed in end order; the shutdown close reuses the normal run attributes) passes every layer and is kept as `alt-grok-run8-fixed` |
| 9 (0.0.6) | 0 | contract 10/15, lifecycle 1/2, P2P pass | three genuine defects: every compaction was exported twice (an entry scan closed the open span, then the `session_compact` handler opened and closed a second one on the same entry); the streaming chat was closed at shutdown with a placeholder end time equal to its start, 300 ms before the verifier's `dispose()` window; and concurrent tool end times were clamped to keep the file monotonic, so the 100 ms call reported 306 ms. The sentence added in 0.0.6 took effect: the shutdown close of `pi.run` carried `turn_count` and its entry id |
| 10 (0.0.6, x0.15, salvaged) | 0 | contract 13/15, lifecycle 2/2, P2P pass | the chain wrapper was killed by host memory pressure; the agent finished in its orphaned container (41 min) and the verifier was run by hand there. Two genuine defects: concurrent tool end lines written in persistence order (as in run 8); and after `/reload` the new process resolved entry ids from the start of the branch, claiming the first prompt's user entry and the first chat entry a second time |
| 11 (0.0.6, x0.15) | 0 | contract 12/15, lifecycle 2/2, P2P pass | one genuine defect behind two cases: the chat span's assistant-entry lookup never consumes the entry it used, so consecutive chats of a steering run (and of a wakeup/continuation chain) all reference the same assistant entry. The third case is a verifier-strictness finding: the compaction end line carried two extra `pi.usage.cache_*` attributes and the verifier compares the compaction attribute map exactly although the instruction never says the table is exhaustive (fixed the same day: the verifier now checks listed keys with correct values for every span kind; under the corrected verifier this submission scores contract 13/15) |
| opus 2 (0.0.6, x0.15) | **1** | all pass | claude-opus-5 via Harbor's claude-code agent, 28 min: the first non-curated pass of the contract-only instruction; kept as `alt-opus-run1`. An earlier attempt the same day was invalid (expired OAuth token, 401 before the first turn) and is not counted |

Both submissions solved 0.0.1 as written (2 of 2 once the clock assumption was removed). Version 0.0.2 adds the live start lines and the failure paths as stated requirements: the trace must survive an aborted stream, a failed compaction, a quit while a run is streaming (open spans closed with status `shutdown`), an unwritable path (reported once, never thrown into pi), and a process killed during a tool execution (the chat span is written at the first `tool_execution_start`). Version 0.0.3 adds three more stated edges: one overlapping span per concurrent tool call, steering and follow-up messages recorded on the run (`pi.run.steer_count`, `pi.run.steer_entry_ids`) instead of opening runs, and the compaction entry's usage and `firstKeptEntryId` on compaction spans. Version 0.0.5 rewrites the instruction into outcome requirements plus an export contract and removes every mechanism it used to prescribe (when to write which span, the propagation variable and its format, how to bind on reload, pi's persistence timing); the verifier was made mechanism-agnostic to match (no variable name, start-line attributes as a minimum, free interleaving at one event, environment restored after a tool). Version 0.0.4 added two more: pi's overflow recovery (the failed chat persisted, an `overflow` compaction with `will_retry`, a retry run with `pi.run.after_compaction` and no message) and sub-agent trace propagation (`PI_AGENT_TRACE_PARENT` published while a tool runs; a child pi joins the parent's trace under that tool span). Version 0.0.6 adds one sentence to the failure-safe requirement: a span closed by a shutdown carries every attribute whose value is known at that moment, an entry id being known only once pi has persisted the entry (the 0.0.5 grok rollout closed the run with no attributes at all; verifier unchanged). The verifier was revised on 2026-09-16 without a version bump: attribute maps of every span kind are checked as listed keys with the right values (extra keys allowed, as the contract never declares the table exhaustive), after a grok submission was failed for two harmless extra attributes on a compaction line. A second revision the same day reviewed every time comparison: the two verifier-clock windows (first-case run start, shutdown window) get 1 ms of slack below as well as above, and the two in-trace comparisons that mix clocks (a turn start, pinned to pi's millisecond event timestamp, against the previous turn's end; a child process's run against the parent's tool span) are made at millisecond granularity, as the shared invariants already were. Trigger: the claude-opus-5 submission's hrtime-anchored clock, permitted by the contract, failed the shutdown case in about one local repeat in four by microseconds and the steering case once in nine by two microseconds. Comparisons between two timestamps of one implementation clock stay exact. Rollouts are recorded in `validation/e2e-evidence.json`.

Details in `validation/e2e-evidence.json` (`real_agent_rollouts`).

## Environment

Identical to `pi-history-notes`: `earendil-works/pi` @
`d981de1229ef899957bbe968bc8dcda02a21f477` (v0.85.1), Node 22.19.0, `npm ci`
from the repository lock, PASS_TO_PASS baseline recorded in the image,
generated from `templates/pi-harbor-node`. No real model is contacted during
verification (no-network, all provider credentials unset, faux provider only).

## Verifier

`tests/test.sh` runs four layers; reward is 1 only if all pass.

| Layer | File | What it observes |
|---|---|---|
| PASS_TO_PASS | `tests/check_pass_to_pass.py` | pi's full coding-agent suite against the in-image baseline (semantic pins in `tests/baseline-pins.json`); existing test files unchanged. |
| Contract (15 cases) | `tests/at.contract.test.ts` | Real `AgentSession` + faux provider; the trace file is parsed strictly against the OTLP/JSON shape, then checked for ids, nesting, end-time order, attribute types and the bijection with the session branch (`traceProblems` in `tests/at_support.ts`); tool failures, error responses, wakeup and continuation runs, manual and threshold compactions, `/reload`, the path override; and the failure paths of 0.0.2: an aborted stream, a failed compaction, a quit while streaming, an unwritable trace path, the live update (the file read while a 1.5-second tool is still running); the 0.0.3 edges: concurrent tool calls, steering and follow-up messages inside a run, compaction summary accounting; and the 0.0.4 edges: pi's overflow recovery (error chat, overflow compaction, retry run) and cross-process trace propagation to a child pi spawned by a tool. |
| Lifecycle (2 cases) | `tests/at.lifecycle.test.ts` | Child pi processes from `dist/`: a second process resumes the session and appends to the same trace with the same trace id and its own `process.pid`; a process killed with SIGKILL during a 20-second tool execution leaves that turn's chat span on disk and the file intact. |
| Integrity | `tests/check_junit.py` | Exact case inventory, zero failures/errors/skips, for both suites. |

## Validation

| Case | Agent | Expected | Result |
|---|---|---|---|
| base | nop | 0 | 0 (no trace file: every case fails) |
| oracle | oracle | 1 | 1 |
| 23 negative controls | oracle + `validation/control-*.patch` | 0 | see `validation/controls-plan.md` |
| alt-grok-run1 | unmodified grok-4.6 rollout 1 submission (0.0.1) | 0 | see `validation/controls-plan.md` |
| alt-grok-run3, alt-grok-run4 | unmodified grok-4.6 rollout submissions (0.0.3) | 0 | passed 0.0.3; under 0.0.4 each fails exactly the overflow-recovery and sub-agent cases |
| alt-grok-run5 | unmodified grok-4.6 rollout submission (0.0.4) | 1 | an independently written correct implementation of 0.0.4 |
| alt-grok-run8-fixed | grok-4.6 rollout 8 submission (0.0.5) plus the 54-line curator fix for its two defects | 1 | an implementation other than the Oracle that satisfies the contract-only instruction (0.0.5/0.0.6): tool end lines buffered until their entries exist and flushed in end order; the shutdown close of `pi.run` carries the same attributes as a normal close |
| alt-opus-run1 | unmodified claude-opus-5 rollout submission (0.0.6) | 1 | an independently written correct implementation of the contract-only instruction |

Local runs use the arm64 build of the same Dockerfile (`ai-infra-bench/pi-history-notes:local`,
retagged) through `tools/local_task_validation.py`; results are in `validation/e2e-evidence.json`.

## Layout

```
pi-agent-trace/
├── .gitattributes
├── instruction.md                 # agent-facing contract
├── task.toml
├── environment/                   # generated from templates/pi-harbor-node (same bytes as the other pi tasks)
├── tests/
│   ├── test.sh, check_junit.py, check_pass_to_pass.py, case_contract.py, baseline-pins.json
│   ├── at_support.ts, at.contract.test.ts, at.lifecycle.test.ts
│   └── fixtures/pi_child.mjs
├── solution/
│   ├── oracle.patch               # extension + README + unit test
│   ├── solve.sh
│   └── README.md
└── validation/
    ├── ci-cases.json              # 23 negative controls + 3 real-agent cases, SHA-256 pinned
    ├── history/0.0.1- to 0.0.4-evidence.json
    ├── control-*.patch
    ├── make_controls.py           # curator-only: derives the controls from the Oracle and pre-checks them
    ├── controls-plan.md, behavior-map.md
    └── e2e-evidence.json
```

## Running

```bash
python3 templates/pi-harbor-node/generate.py --check tasks/pi-agent-trace
python3.12 tools/local_task_validation.py pi-agent-trace ai-infra-bench/pi-agent-trace:local
tools/local_agent_rollout.sh pi-agent-trace ai-infra-bench/pi-agent-trace:local grok-4.6 0.1 tools.harbor_agents.grok_build_oauth:GrokBuildOAuth
```

## Remaining work before publication

1. CI run on the x64 runner and image publication (shared with the other pi tasks).
2. An independent oracle challenge (the alternative implementation exists: `alt-grok-run1`).
3. Ten-dimension review.
