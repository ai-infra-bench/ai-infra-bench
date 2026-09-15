# Pi Plan Mode: upstream history and construction scope

Research date: 2026-09-15. This is validation-only research and must not be placed
inside the agent image or workspace. It records source inspection, not an
executed Base reproducer, accepted Oracle, or completed benchmark review.

## Frozen target and source provenance

- Target: `earendil-works/pi` at
  `d981de1229ef899957bbe968bc8dcda02a21f477` (v0.85.1), cutoff
  `2026-09-05T11:54:46Z`.
- Base files inspected: `packages/coding-agent/examples/extensions/plan-mode/`
  (`index.ts`, README), its file history, and
  `packages/coding-agent/src/core/extensions/types.ts`.
- The Base already includes an official example with `/plan`, `/todos`,
  `Ctrl+Alt+P`, `--plan`, assistant-prose plan extraction, Execute/Stay/Refine,
  tool selection persistence, and progress markers. See the
  [Base README](https://github.com/earendil-works/pi/blob/d981de1229ef899957bbe968bc8dcda02a21f477/packages/coding-agent/examples/extensions/plan-mode/README.md)
  and [Base source](https://github.com/earendil-works/pi/blob/d981de1229ef899957bbe968bc8dcda02a21f477/packages/coding-agent/examples/extensions/plan-mode/index.ts).
- The benchmark contract is independently stated in `instruction.md`: explicit
  submission and revision identity, supported input-source approval, stale UI
  approval rejection, exact tool restoration, and normal file-backed resume.
  Historical reports motivate realistic failure classes; they do not define
  the new task or its correct implementation.
- The Oracle implements this contract. No community package or
  upstream patch has been accepted as the Oracle in this research record.

## Findings and disposition

| Finding and source | Applicability to Base and this task | Disposition / required verification |
| --- | --- | --- |
| [#3109](https://github.com/earendil-works/pi/issues/3109), reported 2026-04-13, and [#3138](https://github.com/earendil-works/pi/issues/3138), reported 2026-04-14: leaving planning overwrote the prior custom tool selection. Both are shown closed. | Base already captures `toolsBeforePlanMode` and restores it; this historical bug must not be claimed to remain unfixed. The new approval workflow must preserve that capability under repeated entry, approval, and normal resume. | Retain exact-tool restoration as a regression contract. Include disabled-read/custom-tool selections; avoid a hardcoded default. Recorded Oracle results are in `e2e-evidence.json`. |
| [#5062](https://github.com/earendil-works/pi/issues/5062), reported 2026-05-27 against 0.75.5, shown closed: action prompts without a plan and execution requiring another message. | This is an older report. Its proposed explanation that custom messages cannot trigger turns must not be imported as a fact about v0.85.1. Base uses queued custom follow-ups, and the task explicitly requires a model-visible custom approved snapshot. | Verify automatic scheduling through the real session path, rather than asserting a chosen send API. Empty/unsubmitted plans must not become approved. |
| [#5428](https://github.com/earendil-works/pi/issues/5428) and [#5327](https://github.com/earendil-works/pi/issues/5327), linked from [#5940](https://github.com/earendil-works/pi/issues/5940): refinement errors and disappearing custom tools. #5327 is shown closed. #5940 was reported 2026-06-21 and is closed. | The upstream fix [542683b29ab2865976dddb006b4d70cffe315e25](https://github.com/earendil-works/pi/commit/542683b29ab2865976dddb006b4d70cffe315e25) explicitly closes #5940 and is an ancestor of Base. It preserves active custom tools, avoids empty-plan prompts and queues refinement/execution follow-ups. | Preserve compatible refinement, execution scheduling, and normal-mode tool selection. Deliberately change planning to the task's restrictive allowlist; do not mistake an old test asserting broad custom-tool access for an immutable requirement. |
| Base Plan Mode source uses a mutable todo list, a boolean planning toggle, prose extraction, and UI choice handling; it does not expose the new `PlanState`/`plan_submit`/`plan-control` contract. | The task is a feature enhancement of an existing extension. Old `/plan` toggle and prose parsing behavior intentionally changes, while helpers and unrelated behavior remain compatible. | Base-versus-Oracle distinction must be demonstrated with supported inputs. In particular, test a displayed revision superseded before UI approval resolves, and current-session/revision validation through the actual input path. |
| Base `ExtensionContext` exposes `isIdle()` and `hasPendingMessages()`; `InputSource` is `interactive \| rpc \| extension`. | These are real public API inputs for the requested workflow. An arbitrary internal object is not enough evidence for an RPC or busy-state test. | Drive the real interactive/RPC input path and a genuinely active/pending session. Prevent extension-origin control text from approving; this is not an OS sandbox against malicious extension code. |

The original example's history also includes the step-tracking contribution
[#694](https://github.com/earendil-works/pi/pull/694) (commit
`e8f1322eeee866c4fb8e8d5f04cb81078595e431`) and shortcut change
[#746](https://github.com/earendil-works/pi/pull/746) (commit
`39ee5fee92c5c4c004fb117382411487ed30fadc`), both visible in local file history.
The new task retains `[DONE:n]` utility behavior and the current shortcut;
neither historical patch is the reference solution for this task.

## Existing public implementations and leakage risk

The following public README snapshots were inspected on the research date.
Community repository heads were not frozen or execution-tested here. Their
descriptions establish existing public ideas, not compatibility with this Base
or compliance with the benchmark's exact contract.

| Public project | Relevant overlap and important difference |
| --- | --- |
| [erasin/pi-plan-mode](https://github.com/erasin/pi-plan-mode) and [Kmiyh/pi-plan-mode](https://github.com/Kmiyh/pi-plan-mode) | Public packages of planning/read-only exploration, extracted numbered steps, execution confirmation and progress tracking. These basic behaviors are not novel. |
| [Mr-remon219/pi-plan-mode](https://github.com/Mr-remon219/pi-plan-mode) | Describes persistent state, reviewed revisions, explicit approval, and resume without automatic execution. It uses a Markdown plan artifact and permits broad exploratory tools, differing from this task's explicit `plan_submit` and strict tool subset. This is substantial conceptual overlap and must be disclosed. |
| [wilfredinni/pi-openplan](https://github.com/wilfredinni/pi-openplan) | Uses structured plan writing/editing and phased execution with progress tracking. Public structured-plan tooling is relevant prior art; no claim is made that its storage, command surface or approval contract matches this task. |

This task must not be advertised as novel or contamination-free. The frozen
image supplies only normal Base source and dependencies, with no community
packages, future checkout, hidden tests, Oracle, or this research file. That
prevents direct environment leakage; it cannot rule out model pretraining
knowledge. Record solver model/version, rollout network policy and any observed
use of public solutions when reporting results. A later held-out task set would
be a separate measurement design, not a property established here.

## Research method and limitations

Inspected local Pi history with `git show`, `git log --all -- <plan-mode path>`,
and `git merge-base --is-ancestor 542683b29ab2865976dddb006b4d70cffe315e25
d981de1229ef899957bbe968bc8dcda02a21f477` (success). All Base behavior claims above refer to explicit reads at the pinned commit.

Public searches included `site:github.com/earendil-works/pi/pull "plan" "mode"`,
`site:github.com/earendil-works/pi/issues "plan-mode" "approval"`, and
`site:github.com/earendil-works/pi "plan-mode" "rpc"`, followed by the linked
issues and source commit. Search covered open/closed material without limiting
to merged PRs. Search indexing and rendered GitHub discussions are incomplete;
this is not an exhaustive audit of all forks, PRs, or unpublished fixes. Closed
issue status alone was not used as evidence of a fix at Base.

Crash recovery, in-flight shutdown, fork/tree navigation, extension reload, and
semantic model compliance are explicitly outside this task. Public packages
that support them do not add hidden requirements. The final construction
evidence must map applicable rows to verifier cases and record actual
Base/Oracle/alternative/control results. No behavioral pass or final acceptance
is claimed in this research note.
