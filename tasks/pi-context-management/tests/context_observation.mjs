// Preloaded before candidate modules; only readonly public Pi observations.
const serialize = JSON.stringify;
const schema = "context-observation.v1";
function observeContextFact(fact) {
  const payload = serialize({ schema, ...fact });
  debugger; // OBSERVATION_PAUSE
}
function observeBoot() {
  observeContextFact({ kind: "boot" });
}
observeBoot();
process.on("exit", function onProcessExit(code) {
  observeContextFact({ kind: "process_exit", exit_code: code });
});
function onFixtureReady() {
  observeContextFact({ kind: "fixture_ready" });
}
let installed = false;
export function installObservationHandlers(pi) {
  if (installed) throw new Error("Context observer installed twice");
  installed = true;
  pi.on("session_start", function onSessionStart(_event, ctx) {
    observeContextFact({ kind: "session_start", session_id: ctx.sessionManager.getSessionId(), session_file: ctx.sessionManager.getSessionFile() });
  });
  pi.on("context", function onContext(event, ctx) {
    const active = new Set(pi.getActiveTools());
    const tools = pi.getAllTools().filter(tool => active.has(tool.name)).map(({ name, description, parameters }) => ({ name, description, parameters }));
    observeContextFact({ kind: "context_ready", session_id: ctx.sessionManager.getSessionId(), messages: event.messages,
      system_prompt: ctx.getSystemPrompt(), tools, tools_json: serialize(tools), model: ctx.model });
  });
  pi.on("before_provider_request", function onProviderRequest(event, ctx) {
    observeContextFact({ kind: "provider_request", session_id: ctx.sessionManager.getSessionId(), api: ctx.model?.api, payload: event.payload });
  });
  pi.on("tool_execution_end", function onToolEnd(event) {
    observeContextFact({ kind: "tool_execution_end", event });
  });
  pi.on("session_before_compact", function onCompaction(event, ctx) {
    observeContextFact({ kind: "compaction_attempt", reason: event.reason, session_id: ctx.sessionManager.getSessionId() });
  });
  pi.on("session_compact", function onCompacted(event, ctx) {
    observeContextFact({ kind: "session_compact", reason: event.reason, from_extension: event.fromExtension,
      session_id: ctx.sessionManager.getSessionId() });
  });
  pi.on("session_compact_failed", function onCompactionFailed(event, ctx) {
    observeContextFact({ kind: "session_compact_failed", event, session_id: ctx.sessionManager.getSessionId() });
  });
  onFixtureReady();
}
