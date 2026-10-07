// The verifier's cooperating tool uses the child-context integration exactly as the
// instruction fixes it: emit `agent-trace:child-env` on pi.events with
// { toolCallId, env, reply }; the extension replies synchronously. This adapter constructs
// no trace ids and reads no candidate state.
import { randomUUID } from "node:crypto";
import { isDeepStrictEqual } from "node:util";

export async function childEnvironment({ pi, toolCallId, env }) {
  function request(id) {
    const original = { ...env };
    const processOriginal = { ...process.env };
    let replyCount = 0;
    let value;
    pi.events.emit("agent-trace:child-env", {
      toolCallId: id,
      env,
      reply: (reply) => {
        replyCount += 1;
        value = reply;
      },
    });
    if (replyCount !== 1) {
      throw new Error(`agent-trace:child-env requires exactly one synchronous reply, received ${replyCount}`);
    }
    if (!isDeepStrictEqual(env, original) || !isDeepStrictEqual({ ...process.env }, processOriginal)) {
      throw new Error("agent-trace:child-env modified its input environment or process.env");
    }
    return value;
  }

  // A public request for an ID that has never been submitted must not borrow
  // the active tool's context. No candidate-specific environment key is assumed.
  if (request(`not-executing-${randomUUID()}`) !== undefined) {
    throw new Error("agent-trace:child-env must reply undefined for a non-executing call ID");
  }
  const childEnv = request(toolCallId);
  if (!childEnv || typeof childEnv !== "object" || childEnv === env) {
    throw new Error("agent-trace:child-env must return an environment copy for an executing tool call");
  }
  return childEnv;
}
