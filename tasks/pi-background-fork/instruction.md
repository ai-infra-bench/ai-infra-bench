When I work with pi on a long task I often want to split off a side investigation ("check whether the other call sites have the same bug") without losing my place and without re-explaining everything to a fresh sub-agent. Add a `fork` tool to pi: the model calls it with a task, a copy of the agent that already knows the whole conversation so far works on that task in the background as a separate pi process, the parent keeps working, and when the fork is done its answer comes back into the parent's conversation.

Implement it as a pi extension at `packages/coding-agent/examples/extensions/fork/index.ts` in this checkout of pi (`@earendil-works/pi-coding-agent` 0.85.1, Node 22). The file must `export default function (pi: ExtensionAPI)` and use only pi's public extension API and exported SDK; do not modify pi core and do not add dependencies. Include a short `README.md` next to the extension, and add a unit test file for it under `packages/coding-agent/test/` that runs offline with `npm test -w packages/coding-agent`. The existing coding-agent test suite must keep passing unchanged; do not edit existing test files.

This document has two parts. **Requirements** say what must be true and are stated as outcomes; how you meet them inside pi is your design. **Interface** fixes the tool and the result message, because the model and other extensions depend on them.

## Requirements

- **Installed like any user extension.** Users install the extension by listing it under `extensions` in the agent directory's `settings.json`, not on the command line, so every pi process that uses those settings loads it.
- **Non-blocking.** Calling `fork` starts the fork and returns at once; the parent's run continues without waiting for the fork to finish. A fork starts working right away, even while other tools of the same assistant message are still running.
- **A separate pi process with the parent's setup.** Each fork is its own pi process running the same pi CLI as the parent process, with the parent's environment, so it has the same agent directory, settings, installed extensions and model providers. It uses the model and thinking level the parent had when it forked. It writes its own session file in the parent's session directory, and that file's header names the parent's session file as `parentSession`. A fork cannot fork: the `fork` tool is not available inside a fork.
- **Inherits the conversation.** A fork's first request to the model starts with the parent's context as the parent's model saw it when it decided to fork: the messages of the request that produced the forking assistant message, in the same order (after a compaction, that is the compacted view), followed by that assistant message. After it come messages that give the fork its task and, recorded in the fork's own session, a result for every tool call of that assistant message. The task is the fork's only new instruction, and nothing the parent does after the fork ever reaches the fork. A fork works without a user and finishes when its agent run ends.
- **Result delivery.** When a fork finishes, its result is added to the parent session once and reaches the parent's model. If the parent is not in an agent run (idle, or busy with something else such as compacting), the result starts a new run as soon as the parent can take one. If the parent is running, its model sees the result in a later request of the same run, and tools that are executing are not interrupted. Interrupting the parent does not lose a result: when the user presses Escape, pi aborts the run and discards the messages queued for it, and a result that had not reached the parent's model yet is then delivered once the parent is idle, still exactly once.
- **Failures are reported.** A fork whose process exits abnormally or is killed, or whose last model response ended with an error, still produces exactly one result, with the status `failed` and the reason (for a model error, the error message the provider returned).
- **Concurrent.** Any number of forks can run at once, including several forks called in one assistant message, and each result is attributed to its own fork.
- **Owned by the session.** A running fork belongs to the parent session that started it. When that session ends, because the parent process quits or the user switches to another session (new, resume, fork or clone), its running forks are stopped within 5 seconds and deliver nothing, to that session or to any other. If the parent process dies without shutting down (for example it is killed), its forks stop on their own within 5 seconds. Reloading extensions (`/reload`) does not end the session: forks keep running and deliver their result exactly once.

## Interface

### Tool

The tool is named `fork` and takes `{ "task": string }`. A task that is empty or only whitespace is rejected with an error result and starts nothing. Otherwise the tool returns once the fork's process has started: the result text names the fork id, and the result `details` are `{ "forkId": string }`, a non-empty id that is unique among the forks of the parent session.

### Result message

A fork's result is a custom message in the parent session with `customType: "fork-result"` and `display: true`. Its content includes, verbatim, the text of the fork's final assistant message for a completed fork, or the failure reason for a failed one. Its `details` are:

```json
{ "forkId": "<id from the tool result>", "status": "completed" | "failed", "sessionFile": "<absolute path of the fork's session file>", "error": "<reason; failed only>" }
```

`sessionFile` is omitted only when the fork never created a session file.
