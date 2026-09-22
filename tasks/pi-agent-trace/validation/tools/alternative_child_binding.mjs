// Manual adapter transcribed from this alternative's README public protocol.
// Does not import the candidate implementation or inspect its private state.
export async function childEnvironment({ pi, toolCallId, env }) {
  let result;
  pi.events.emit("agent-trace:request-child-context", {
    callId: toolCallId,
    baseEnv: env,
    accept(value) { result = value; },
  });
  if (!result) throw new Error("No active trace context for this tool call");
  return result;
}
