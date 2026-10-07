# Constructing agent-harness (pi) tasks

Use this playbook for ai-infra-bench tasks whose target repository is a coding
agent harness (today: `earendil-works/pi`) and whose deliverable is an
extension or a core change judged by a deterministic verifier. It supplements
the generic workflow and the vLLM playbook; the independent review remains
governed by the `ai-infra-bench-task-review` skill.

Every rule below comes from a defect that cost a real rollout (a judge that
scored a correct submission 0, or an instruction that let two readings pass).
Do not reintroduce them.

## Contents

1. [Verifier shape](#1-verifier-shape)
2. [Timing and precision](#2-timing-and-precision)
3. [pi facts: stated versus discovered](#3-pi-facts-what-the-contract-states-and-what-the-solver-discovers)
4. [Instruction wording](#4-instruction-wording)
5. [Base, controls and real submissions](#5-base-controls-and-real-submissions)
6. [Process hygiene during validation](#6-process-hygiene-during-validation)

## 1. Verifier shape

- Four layers, reward 1 only when all pass: PASS_TO_PASS (pi's own vitest
  suite against an in-image Base baseline with semantic pins), contract (a
  real `AgentSession` driven by pi's first-party faux provider), lifecycle
  (separate child pi processes loaded from `dist/`), integrity (JUnit
  inventory equals `case_contract.py`, zero skips; vitest exit code is part of
  the reward). Never contact a real model: `no-network`, every provider
  credential unset, `PI_OFFLINE=1`.
- The verifier observes public surfaces only: tool results, the session tree
  (`getBranch()`), provider request contexts captured through faux response
  factories, the event stream, files under the session directory, child
  processes. It never imports candidate code and never compares to the Oracle.
- Every case must fail on Base **on behaviour**, with a readable reason
  (`Tool x not found`, `trace file … does not exist`). A helper that throws
  on an empty workspace (an early return missing a field, `undefined is not
  iterable`) is a verifier bug even when the reward is unchanged. Run the Base
  pre-check and read its failure messages before freezing.
- Keep a curator script that derives every control patch from the Oracle
  source, runs both suites for Oracle, Base, every control and every real
  submission, and pins the patch SHA-256s. Controls are full diffs against
  Base; candidate patches may add files outside the Oracle's paths, so the
  cleanup must remove every path the patch touched.

## 2. Timing and precision

These produced two of the four judge defects found by real rollouts.

- Never assert equality of timestamps between two spans, events or records.
  An implementation may read the clock once per record, add sub-millisecond
  digits, or bump a monotonic counter. Compare timestamps only against a
  window the verifier observed itself (`Date.now()` before and after the
  action, with one millisecond of slack on each side) and against ordering
  constraints (child before parent in the file, end times non-decreasing).
- When the contract pins a timestamp to a pi event field (a turn starts at
  the `turn_start` event's `timestamp`), compare at millisecond precision and
  say in the contract that sub-millisecond digits belong to the implementation.
- Wording such as "at that moment" or "immediately" must be backed by a
  measurable definition in the verifier (a window, an order), never by
  equality.
- Ordering checks between records (turns do not overlap, a child lies inside
  its parent, a tool starts after the chat ended) compare at millisecond
  granularity too: two records stamped in the same millisecond are neither
  ordered nor overlapping, whatever their sub-millisecond digits say. A strict
  nanosecond comparison rejected a correct submission whose end times carried a
  monotonic +1 ns bump.
- Do not bound durations from below unless the verifier itself introduced the
  delay (a tool that sleeps 30 ms may be asserted to have lasted 25 ms or more).
- Automatic compaction ignores usage from an assistant message stamped in the
  same millisecond as the last compaction entry: when a case chains a manual
  compaction and a threshold compaction, put a short turn and a few
  milliseconds between them.

- Slack must apply below the window as well as above it, and it must reach
  every assertion, not only the shared helpers. A submission may build its clock
  as `Date.now()` read once at load, truncated to the millisecond, plus an
  `hrtime` offset (an OpenTelemetry-style clock): it then reads up to one
  millisecond *behind* the verifier's `Date.now()` for the whole session. On
  pi-agent-trace such a submission passed the Harbor run and then failed the
  shutdown window's exact lower bound in two local repeats out of eight, by 16
  microseconds, and failed a per-case turn-order assertion (`turn.start >=
  previousTurn.end` at nanosecond precision, while the shared invariant already
  compared in milliseconds) once in nine. Before recording a passing real
  submission as an expected-1 control, repeat the verifier against it eight to
  ten times in the task image; a control that flakes is worse than none.

## 2b. Scoring trust in the shared container

Harbor runs the verifier in the container the agent just used. Whatever the agent
could write, the verifier will execute: with a root agent, replacing
`node_modules/vitest/vitest.mjs` with a script that parses the `it(...)` titles of the
files it is asked to run and emits a passing JUnit report earned reward 1 on Base for
both pi tasks (task review of 2026-09-17). An exact JUnit inventory, a forged-report
control and an early-exit control do not cover a replaced runner.

- Run the agent as the image's unprivileged user (`[agent].user = "node"`, a native
  Harbor field) and leave `node_modules`, `node`, `python3` and `bash` root-owned and
  read-only for it; give vite writable `node_modules/.vite-temp` and `.vite` dirs. Check
  the agent can still run the project's tests, `git apply` and type-check before
  relying on it. Run every suite that executes candidate code as that user too, and let
  only root write the reward.
- In `test.sh`, reject submissions that changed project source or the build/test
  toolchain (test configs, manifests, scripts) before running any suite; a tracked
  `vitest.config.ts` is loaded by the verifier's own run. Keep the rule narrow so a
  stray scratch file does not fail a correct extension. Remove vite's transient
  bundles before running.
- Decide what changed by content, never by git. The checkout and its `.git` belong to
  the agent: `git update-index --assume-unchanged`, a `.gitignore` line or
  `.git/info/exclude` hide an edit from `git status`, and git run as root in that
  checkout executes whatever `.git/config` names (`core.fsmonitor`, `diff.external`):
  on harness revision 4 of the pi tasks the verifier's own `git status` ran a
  candidate hook as uid 0 (reproduced 2026-09-19). Root never runs git there; an
  informational diff snapshot is taken as the unprivileged user. Hash the protected
  Base files against a manifest shipped in `tests/` (derived from the Base commit,
  identical across platforms; `templates/pi-harbor-node/base_manifest.py`).
- Protect what the suites actually execute, not only what git tracks. The built
  `dist/` trees are gitignored, agent-owned, and are what a lifecycle suite spawns;
  their bytes depend on the image build, so the image records them root-owned
  (`/opt/pi-baseline/build-manifest.sha256`) and the verifier compares against that. A
  rebuild from unchanged sources reproduces the bytes, so honest rebuilds pass.
- Repeat the scope check after the suites: candidate tests and the extension run as
  the owner of the checkout during verification.
- Do not pipe a bash function that sets a result variable (`check | tee log` runs it in
  a subshell and the variable is lost); redirect to a file instead.
- Keep controls on top of the Oracle (expected 0) so the scope check is itself
  validated: an edited test config, a core file hidden by `.gitignore`, a candidate
  test that edits the built `dist/` during verification. Bypasses a patch cannot
  express (`.git` state, agent-phase edits of gitignored output) go in a probe script
  (`validation/tools/scope_bypass_probe.sh` in the pi tasks).
- Screen every reward-1 rollout with `tools/rollout_hack_screen.py` before recording
  it as a pass.

## 3. pi facts: what the contract states and what the solver discovers

Write the instruction in two parts: **requirements** stated as outcomes (what
must be true of the artifact, in the user's terms) and an **export contract**
(file format, names, attribute keys, status rules, entry bindings) that the
judge depends on. Never state the mechanism: which event to write on, which
environment variable to use, how to bind on reload. A solver that is handed
the design passes on the first attempt and the task measures nothing.

The pi facts below are the ones a natural implementation gets wrong. They are
discoverable in the pi source and in the faux-driven tests a solver can write,
so they belong in the instruction only when the judge depends on a specific
reading of them (an error-text prefix that pi's own validation would
pre-empt, a units definition). When a rollout fails on one that is not
stated, attribute it to the agent and keep the instruction; when it fails
because the instruction implied a different reading, fix the instruction.

- pi persists a message **after** extensions have seen its `message_end`, so
  a session entry id exists only at the next event (`tool_execution_start`
  or `turn_end` for the assistant message, `turn_end` for tool results).
- pi validates tool parameters against the tool's schema before `execute`
  runs and reports failures in its own words. If the contract requires
  prefixed error text for out-of-range arguments, say that schemas must stay
  permissive (a nullable string rather than an enum) so the extension itself
  rejects the value. A parameter type literal such as `role?: "user" | "tool"`
  invites the enum; either avoid the literal or add the sentence.
- `session_start` reaches a reloaded extension runtime only when the host
  bound UI or command contexts; headless SDK use gets none. Bind to the
  session lazily from the `ctx.sessionManager` of whatever event comes first.
- `session_shutdown` reaches extensions on `/reload`, session switches and
  `runtime.dispose()` (which does not abort a streaming run first); the SDK's
  `session.dispose()` sends nothing.
- Extension handler exceptions are swallowed by pi and reported to an error
  listener; the agent keeps running. A contract about "never throwing into pi"
  is observable through `bindExtensions({ onError })`.
- `sendMessage` with `triggerTurn: false` while streaming is flushed at
  `turn_end` and emits no extension `message_*` events; `deliverAs: "steer"`
  or `"followUp"` while streaming starts a new turn inside the same run; a
  follow-up queued from an `agent_end` handler starts a new run before
  `agent_settled` (a continuation).
- The faux provider never calls `onPayload`, so `before_provider_request`
  never fires offline; it does call `onResponse`. `tokensPerSecond` slows the
  stream so a case can abort or shut down mid-turn; an error-stopReason
  response queued for the summary makes a compaction fail deterministically.
- Tool calls of one assistant message run concurrently (start, start, end,
  end); design tool bookkeeping and cases around overlap.

## 4. Instruction wording

- Define units: characters are UTF-16 code units (JavaScript `length` and
  `slice`), bytes are UTF-8; say how lines are split and what a trailing
  newline produces; say what "clamped" means for each bound.
- Specify what must be omitted, not only what must be present (an error span
  carries no entry id; a start line carries no status).
- Every behaviour the verifier asserts must be one sentence a solver can
  point at, phrased as an outcome ("a process that dies during a tool leaves
  that turn's chat span on disk"), not as a mechanism ("write the chat span
  at the first tool_execution_start"). The verifier then checks the outcome
  (kill during a tool, read the file), which any mechanism can satisfy. When a rollout fails a case and the sentence is missing, the fix
  is the instruction (or the assertion), never the score.
- Difficulty comes from stated, deterministic edges that a natural
  implementation misses (cross-process locks, crash safety, shutdown
  flushes, concurrency), never from leaving the contract loose.

## 5. Base, controls and real submissions

- Keep every real-agent submission as a validation case
  (`validation/patches/<name>.patch`) with the reward it actually earns under the
  current verifier, and say why in the pull request.
  A submission that passed an earlier revision and fails the current one is
  the best evidence that a new edge discriminates; a submission that passes
  unmodified is the alternative implementation the review asks for.
- Results, review reports and rollout write-ups live with the CI or Harbor run
  records and in the pull request, not in the task directory
  (`templates/harbor-task/README.md`, "Validation layout"); earlier records stay
  reachable through Git history. Do not reuse results after an executable or
  contract-changing edit.
- Attribute every rollout failure as judge over-specification, instruction
  ambiguity, or agent defect, and say which in the pull request.

## 6. Process hygiene during validation

- Two Harbor jobs on one machine (a matrix and a rollout, or two rollouts)
  have killed the orchestrator under memory pressure. Run them sequentially.
- A background "wait until free, then run" loop is itself a launcher. When a
  job is cancelled, kill the loop that would restart it, and confirm with
  `ps` that no waiter remains before promising another session the machine.
- Rollouts copy the task directory when they start: do not edit `tests/` or
  `instruction.md` while one is queued or running, or record which revision
  each run saw.
