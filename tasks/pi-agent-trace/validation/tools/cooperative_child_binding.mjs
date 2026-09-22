// Curator mapping of the Oracle README's public event-bus integration.
// The candidate selects all context values; this adapter constructs no trace IDs.
export async function childEnvironment({ pi, toolCallId, env }) {
  let childEnv;
  pi.events.emit("agent-trace:child-env", {
    toolCallId, env, reply: (value) => { childEnv = value; },
  });
  if (!childEnv) throw new Error("Documented child-env API returned no active tool environment");
  return childEnv;
}
