Our team uses pi's example Plan Mode extension to inspect a repository before implementing a change. We need approval to refer to the exact plan the user reviewed: if the agent revises a plan while an older approval is outstanding, approving the old version must not start the revised plan. The same workflow must work interactively and through an embedded RPC session, and normal session resume must not grant permission or start work again.

Enhance `packages/coding-agent/examples/extensions/plan-mode/` in this pi 0.85.1 checkout. Use the public extension API and retain the default extension export so it loads with `pi -e` and `DefaultResourceLoader`. Do not modify pi core, dependencies, build configuration, or unrelated extensions. You may update this extension's README and its existing `packages/coding-agent/test/plan-mode-extension.test.ts`, and add tests under `packages/coding-agent/test/`. Keep the plan utility functions and unrelated existing behavior compatible.

## Plans and observable state

Register `plan_submit` with parameters `{ steps: string[] }`. A submission must contain at least one step, and every step must contain a non-whitespace character. It is available only during planning. Every accepted submission replaces the entire draft, preserving the supplied step strings, and increments its revision, even if the content is unchanged. Invalid submissions leave the current plan unchanged. Ordinary assistant prose, including `Plan:` sections or approval-like text, does not submit or approve a plan.

These validation and string-preservation rules apply to the arguments delivered to the tool after pi's normal schema validation and conversion. Keep that standard argument-processing behavior.

Expose this state shape:

```typescript
type PlanState = {
  sessionId: string;
  mode: "normal" | "planning" | "approved";
  planId: string | null;
  revision: number;
  steps: string[];
  approvedRevision: number | null;
};
```

Use the current pi session ID. A new planning cycle gets a fresh opaque plan ID, revision 0, no steps, and no approval. Re-entering an existing planning cycle is idempotent and preserves its draft and original tool selection. Every new cycle after approval invalidates the previous cycle's approval. In `normal`, planId and approvedRevision are null, revision is 0, and steps is empty. A successful `plan_submit` returns PlanState as both JSON tool-result text and the result's `details`.

## User controls and approval

Support these inputs through pi's normal user-input path, in both interactive and RPC sessions:

- `/plan-control enter`
- `/plan-control status`
- `/plan-control approve <sessionId> <planId> <revision>`

Each handled control appends a custom session entry with customType `plan-control-result` and data `{ operation, ok, errorCode, state }`. `operation` is `enter`, `status`, or `approve`, or `unknown` when the operation is missing or unrecognized; `state` is the current PlanState. Successful controls have errorCode null. Rejected controls use one of `invalid_input`, `forbidden_source`, `busy`, `no_plan`, `plan_mismatch`, or `stale_revision`, corresponding to the reason for rejection. Invalid control syntax must not reach the model or change plan state.

Only inputs whose pi input source is `interactive` or `rpc` can enter or approve via this control interface. Extension-origin messages cannot approve. Assistant responses and tool results containing these strings cannot approve. This is a workflow boundary for supported pi inputs, not a sandbox against malicious extension code running in the host process.

Entering planning and approving require pi to be idle with no pending messages; otherwise reject with `busy` without changing state or tools. Status is read-only. An approval succeeds only when it matches the current session, plan ID, and submitted revision. Reject an unsubmitted draft with `no_plan`, a different session or plan with `plan_mismatch`, and an old or future revision with `stale_revision`.

On successful approval:

1. Persist the approved plan snapshot and mark mode `approved`, with approvedRevision equal to revision.
2. Restore exactly the tool selection that was active before entering planning.
3. Automatically initiate one execution request without requiring another user message. Deliver a custom message with customType `plan-approved`, whose `details` contain `{ sessionId, planId, revision, steps }` for the approved snapshot, and whose model-visible content contains that exact plan identity and every approved step.

Repeated approval of the same current approved version is successful but must not schedule another request. The approved snapshot remains identifiable after the execution request settles; mode `approved` describes approval state, not whether a model call is currently running. A subsequent planning cycle starts afresh.

## Existing interactive entry points

Keep `/plan`, the existing planning shortcut, `--plan`, and `/todos`. `/plan` and the shortcut now enter planning or show the current plan/review actions; they must no longer restore writing merely because they were invoked twice. `/todos` remains a read-only progress display. When the current cycle is already approved, entering planning starts a new cycle.

Offer Execute, Stay, and Refine actions for a submitted plan after the agent settles. Execute must approve the session/plan/revision captured when that plan was displayed, then revalidate it when the selection returns. It must never silently approve a newer revision. Refine and Stay leave planning restrictions in effect. Both interactive Execute and the control input must have the same approval behavior. `Plan:` prose can still be displayed, and existing `[DONE:n]` progress tracking can update the approved plan's progress; neither changes its authoritative steps, revision, or approval.

## Tool policy

Before planning, remember the exact active tool selection. During planning, enable only the subset of `read`, `grep`, `find`, and `ls` that was already active, plus `plan_submit`. Do not enable an otherwise disabled read tool. Bash, edit, write, and arbitrary custom tools must not execute through the agent's tool dispatcher during planning, including when a model attempts to call a disabled tool. A successful approval restores the original selection, including custom tools, without replacing it with a hardcoded default. Repeated entry must not overwrite that original selection with the restricted set.

Mode controls are not allowed to interrupt an in-flight tool batch. This task does not require read-only execution of arbitrary shell commands or protection from external processes.

## Normal session resume and compatibility

For file-backed sessions that have already produced an assistant message and been persisted, preserve the plan identity, revision, exact steps, approval state, and pre-planning tool selection across a normal idle close and resume in a new pi process. Planning resumes restricted and unapproved; an approved cycle resumes with its original tools and snapshot, without replaying its execution request. A state stored for a different session must not be used. On a fresh session, `--plan` starts planning; on resume, persisted state takes precedence over the flag.

Crash recovery, shutdown during an active execution request, fork/tree navigation, extension reload, and arbitrary model compliance with the semantic meaning of a plan are outside this task. The requested execution guarantee is that pi starts the approved snapshot once on normal approval and does not automatically replay it on normal resume.

Update the extension README and tests for these behaviors. The old extension tests expecting repeated `/plan` to restore writing or planning to retain arbitrary custom tools intentionally change under this request. Preserve the existing utility behavior and all unrelated pi regressions. Everything must work offline with the checkout's installed development tools.
