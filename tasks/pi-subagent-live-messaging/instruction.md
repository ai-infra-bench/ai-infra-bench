# Share discoveries between running Pi subagents

I use Pi's subagent extension to investigate and implement changes in parallel. When one worker discovers an interface constraint or rules out an approach, I want its teammates to use that finding while they are still working, without waiting for all tasks to finish or asking the parent to relay it.

Add optional communication within one parallel dispatch in `packages/coding-agent/examples/extensions/subagent/`. Workers should be able to discover their teammates, send a private message to a particular teammate, and broadcast to all running teammates. Each worker must be independently addressable, even when several tasks use the same agent definition. Keep workers as separate Pi processes.

Incoming findings should automatically enter the recipient's model context with the actual sender's identity and complete text. Sending must not wait for a reply, and receiving must not require the model to poll an inbox. A message accepted before the current model response and its tool calls finish must appear in the recipient's next model call. If the worker would otherwise finish there, it must process accepted messages before exiting. Do not interrupt running tools to deliver messages.

During normal execution, deliver accepted messages once and preserve each sender's order to each recipient. Support Unicode findings without silently truncating them. Send only to running teammates, excluding the sender, and clearly report unsuccessful recipients, including partial broadcast failures. Reject invalid requests or unsupported message sizes explicitly. A successful send means acceptance for delivery; it must not race with shutdown and silently lose the message. Later sends must not restart finished workers.

Keep each dispatch's messages private to its team, including when a parent launches multiple teams or reuses task identities. Cancelling the parent must stop its children and clean up communication resources. Later dispatches must not receive old messages. Preserve existing subagent behavior and configuration when communication is disabled.

Use the existing subagent entry point. Choose and document how to enable communication, address workers, and expose the communication tools; new tool names, arguments, return formats, and transport are up to you. Include usage examples. Cross-session communication, crash recovery, nested teams, persistent shared memory, and a new UI are outside scope.

Work in `/workspace/pi` with the installed dependencies and deliver code and documentation changes. Pi runs directly from TypeScript source. The six pre-existing provider/catalog errors in `npm run check` are unrelated to this task.
