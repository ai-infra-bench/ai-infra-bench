// The verifier's cooperating tool uses the child-context integration exactly as the
// instruction fixes it: emit `agent-trace:child-env` on pi.events with
// { toolCallId, env, reply }; the extension replies synchronously. This adapter constructs
// no trace ids and reads no candidate state.
export async function childEnvironment({ pi, toolCallId, env }) {
  let childEnv;
  let replied = false;
  pi.events.emit("agent-trace:child-env", {
    toolCallId,
    env,
    reply: (value) => {
      replied = true;
      childEnv = value;
    },
  });
  if (!replied) throw new Error("agent-trace:child-env got no synchronous reply");
  if (!childEnv) throw new Error("agent-trace:child-env replied undefined for an executing tool call");
  return childEnv;
}
