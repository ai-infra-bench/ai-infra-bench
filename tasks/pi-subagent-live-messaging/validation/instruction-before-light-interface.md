# Share discoveries between running Pi subagents

We use Pi's subagent extension to investigate and implement changes in parallel. A worker often discovers an interface constraint or a failed approach while its teammates are still working. We need it to share that finding immediately, so another worker can use it in its next step without waiting for the whole investigation to finish or asking the parent to relay it.

Extend `packages/coding-agent/examples/extensions/subagent/` with opt-in communication for one parallel dispatch. Add `communication?: boolean` to the existing `subagent` tool arguments and `id?: string` to each parallel task. With communication enabled, every task must have a distinct nonempty ID; reject invalid requests before starting children. IDs identify worker instances, so two tasks using the same agent definition must remain independently addressable. Keep workers as separate Pi processes.

Expose these tools to participating workers:

- `team_members({})` returns `{ self: string, members: [{ id: string, agent: string, state: "pending" | "running" | "finished" }] }`. Include all tasks in this dispatch; `self` is the caller's task ID.
- `team_send({ to?: string, broadcast?: boolean, message: string })` sends a nonempty text message. Require exactly one of a nonempty `to` or `broadcast: true`. Return `{ accepted: string[], failed: [{ id: string, reason: string }] }`. A direct send to an unknown, pending, finished, or self recipient must fail clearly. Broadcast targets all currently running teammates except the sender; partial failures must be reported per recipient. Reject malformed arguments as tool errors. Support Unicode and messages of at least 16 KiB in UTF-8; reject an unsupported size rather than silently truncating it.

Sending must not wait for a reply. Success means the message has been accepted for delivery, not that the recipient has read or agreed with it. Attribute messages to the actual sending task ID. Incoming messages must enter the recipient's model context automatically, preserving the sender and full text. No model-visible inbox-polling tool call is required.

Delivery may wait for the current model response and its tool calls to finish, but a message accepted before that boundary must be present in the recipient's next model call. If the recipient would otherwise finish at that boundary, it must process already accepted messages before exiting. Do not abort a running tool merely to deliver a finding. Preserve each sender's order to each recipient, and inject each accepted message once during normal execution. No total ordering between different senders is required.

Each dispatch forms an independent team, even when multiple dispatches share a parent session, task IDs, agent definitions, or working directory. Messages must not cross team boundaries. Handle sends racing with completion without reporting acceptance and then silently dropping the message. Finished workers are not restarted by later sends. Parent cancellation must stop its children and release the team's communication resources; a later dispatch must not receive old messages.

Preserve ordinary single, parallel, and chained subagent execution when communication is disabled. Keep the existing model/tool configuration, progress reporting, final result collection, concurrency limits, and error behavior. Document how to enable communication and how workers send and receive findings. The transport and internal storage are your choice. Crash recovery, independent Pi sessions joining teams, recursive teams, persistent shared memory, and a new UI are outside scope.

Work in `/workspace/pi` with the installed dependencies. Deliver implementation and documentation as repository changes.

Environment note: `pi` runs directly from TypeScript source. The frozen Base has six pre-existing provider/catalog type errors in the repository-wide `npm run check`; those unrelated errors are not acceptance criteria for this task.
