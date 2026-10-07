# Share discoveries between running Pi subagents

I use Pi's subagent extension to investigate and implement changes in parallel. When one worker discovers an interface constraint or rules out an approach, I want its teammates to use that finding while they are still working, without waiting for all tasks to finish or asking the parent to relay it.

Add optional communication within one parallel dispatch in `packages/coding-agent/examples/extensions/subagent/`. Workers should be able to discover their teammates, send a private message to a particular teammate, and broadcast to the rest of the team. Each worker must be independently addressable, even when several tasks use the same agent definition. Keep workers as separate Pi processes.

Incoming findings should automatically enter the recipient's model context with the actual sender's identity and complete text. Sending must not wait for a reply, and receiving must not require the model to poll an inbox. A message accepted before the current model response and its tool calls finish must appear in the recipient's next model call. If the worker would otherwise finish there, it must process accepted messages before exiting. Do not interrupt running tools to deliver messages.

During normal execution, deliver accepted messages once and preserve each sender's order to each recipient. Support Unicode findings without silently truncating them. Send only to running teammates, excluding the sender, and clearly report unsuccessful recipients, including partial broadcast failures. Reject invalid requests or unsupported message sizes explicitly. A successful send means acceptance for delivery; it must not race with shutdown and silently lose the message. Later sends must not restart finished workers.

Keep each dispatch's messages private to its team, including when a parent launches multiple teams or reuses task identities. Cancelling the parent must stop its children and clean up communication resources. Later dispatches must not receive old messages. Preserve existing subagent behavior and configuration when communication is disabled.

Use the existing subagent entry point and this public interface; the transport and internal design are yours. The extension is installed as its README documents, in the agent directory's `extensions/subagent/`, so every Pi process that uses that agent directory, workers included, discovers it:

- Enabling: a parallel `subagent` call with `communication: true`. Each entry in `tasks` then has an `id` string, unique within the dispatch, which is that worker's address.
- Each worker in such a dispatch has two tools, `team_members` and `team_send`. Each returns a single JSON object as its whole text result.
- `team_members` takes `{}` and returns `{"self": "<caller id>", "members": [{"id": "<id>"}, ...]}`. `members` has no duplicates and contains only workers of the caller's own dispatch. It includes every running teammate and may also list the caller or workers that are not running. Extra fields are allowed.
- `team_send` takes `{"to": "<id>", "message": "<text>"}` for one teammate, or `{"broadcast": true, "message": "<text>"}` for every other worker in the dispatch. It returns `{"accepted": ["<id>", ...], "failed": [{"id": "<id>", "reason": "<non-empty text>"}, ...]}`. An unknown id, the sender itself, and a teammate that is not running (for example one that has already finished) are reported in `failed` of a normal result, not as a tool error. This includes each such teammate addressed by a broadcast, while the running ones are accepted.
- A malformed request, such as one with no recipient, with both `to` and `broadcast`, or with a non-string `message`, is rejected. So is a message over the limit. Rejection is either a tool error or a result with empty `accepted` and non-empty `failed`, and nothing is delivered.
- Messages of up to 1 MiB (1,048,576 bytes of UTF-8) are accepted and delivered intact. Larger messages are rejected.
- A delivered message appears in the recipient's model context with its complete text and the sender's `id`, in the same model-visible message.
- After a cancelled dispatch has stopped, no file anywhere its workers could write may still contain that dispatch's undelivered message text.

Document the feature with usage examples. Cross-session communication, crash recovery, nested teams, persistent shared memory, and a new UI are outside scope.

Work in `/workspace/pi` with the installed dependencies and deliver code and documentation changes. Pi runs directly from TypeScript source. The six pre-existing provider/catalog errors in `npm run check` are unrelated to this task.
