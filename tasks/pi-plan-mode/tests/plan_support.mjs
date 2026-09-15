/** Verifier host: real SDK, resource loader, faux provider and file-backed sessions. */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import { Type } from "typebox";
import { fauxProvider, fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager, initTheme } from "@earendil-works/pi-coding-agent";

export const WORKSPACE = process.env.PI_WORKSPACE ?? "/workspace/pi";
export const EXTENSION = join(WORKSPACE, "packages/coding-agent/examples/extensions/plan-mode/index.ts");
export const DEFAULT_TOOLS = ["read", "write", "bash", "edit", "grep", "find", "ls", "verifier_effect", "verifier_wait"];
export const say = (text) => fauxAssistantMessage(text);
export const call = (name, args, id = randomUUID()) => fauxAssistantMessage(fauxToolCall(name, args, { id }), { stopReason: "toolUse" });
export const textOf = (message) => typeof message.content === "string" ? message.content : (message.content ?? []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
export function deferred() {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
}
export async function waitFor(probe, label = "condition", timeout = 6000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    const found = probe();
    if (found) return found;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error(`Timed out: ${label}`);
}
export function makeBox() {
  const root = mkdtempSync(join(tmpdir(), "pi-plan-verifier-"));
  const box = { root, cwd: join(root, "project"), agentDir: join(root, "agent"), sessionDir: join(root, "sessions") };
  for (const path of [box.cwd, box.agentDir, box.sessionDir]) mkdirSync(path, { recursive: true });
  return box;
}
export async function start(options = {}) {
  initTheme("dark", false);
  const box = options.box ?? makeBox();
  const tag = options.tag ?? randomUUID();
  const faux = fauxProvider({ provider: "plan-verifier", api: "plan-verifier-api", models: [{ id: "plan-verifier-model", contextWindow: 200000, maxTokens: 8192 }] });
  const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const requests = [], events = [], errors = [], dialogs = [], notices = [];
  const gate = deferred(), started = deferred();
  let api;
  const resourceLoader = new DefaultResourceLoader({
    cwd: box.cwd, agentDir: box.agentDir, settingsManager,
    additionalExtensionPaths: [EXTENSION],
    extensionFactories: [{ name: `plan-verifier-${tag}`, factory: (pi) => {
      api = pi;
      pi.registerProvider(faux.provider);
      pi.registerTool({ name: "verifier_effect", label: "Verifier effect", description: "Append a marker to a real file", parameters: Type.Object({ path: Type.String(), marker: Type.String() }),
        async execute(_id, params) { appendFileSync(params.path, `${params.marker}\n`); return { content: [{ type: "text", text: params.marker }], details: { marker: params.marker } }; }
      });
      pi.registerTool({ name: "verifier_wait", label: "Verifier wait", description: "Wait for host release", parameters: Type.Object({}),
        async execute() { started.resolve(); await gate.promise; return { content: [{ type: "text", text: "released" }], details: {} }; }
      });
      if (options.blockRead) pi.on("tool_call", async (event) => { if (event.toolName === "read") { started.resolve(); await gate.promise; } });
      if (options.foreignEntry) pi.on("session_start", () => pi.appendEntry(options.foreignEntry.customType, options.foreignEntry.data));
    }}],
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    systemPrompt: "Deterministic benchmark provider; obey the scripted protocol."
  });
  await resourceLoader.reload();
  const loadErrors = resourceLoader.getExtensions().errors;
  if (loadErrors.length) throw new Error(`Extension load errors: ${JSON.stringify(loadErrors)}`);
  const sessionManager = options.sessionFile ? SessionManager.open(options.sessionFile, dirname(options.sessionFile)) : SessionManager.create(box.cwd, box.sessionDir);
  for (const entry of options.seedEntries ?? []) if (entry.type === "custom") sessionManager.appendCustomEntry(entry.customType, entry.data);
  const { session } = await createAgentSession({ cwd: box.cwd, agentDir: box.agentDir, model: faux.getModel(), thinkingLevel: "off", resourceLoader, sessionManager, settingsManager });
  session.setActiveToolsByName(options.activeTools ?? DEFAULT_TOOLS);
  session.extensionRunner.setFlagValue("plan", Boolean(options.flag));
  const ui = { ...session.extensionRunner.getUIContext(),
    notify: (message, type) => notices.push({ message, type }),
    select: async (title, choices) => {
      const answer = deferred();
      const dialog = { title, choices, answer, choose: (kind) => {
        const choice = choices.find((value) => value.toLowerCase().includes(kind.toLowerCase()));
        if (!choice) throw new Error(`Missing ${kind} action: ${JSON.stringify(choices)}`);
        answer.resolve(choice);
      }};
      dialogs.push(dialog);
      if (!options.deferUI) {
        const stay = choices.find((value) => /stay/i.test(value));
        answer.resolve(stay);
      }
      return answer.promise;
    },
    editor: async () => options.refinement ?? "Refine without executing",
  };
  session.subscribe((event) => events.push(event));
  const bind = { mode: options.ui ? "interactive" : "rpc", onError: (error) => errors.push(error) };
  if (options.ui) bind.uiContext = ui;
  await session.bindExtensions(bind);
  const live = { box, session, sessionManager, faux, requests, events, errors, dialogs, notices, api,
    waitStarted: started.promise, release: gate.resolve,
    tools: () => session.getActiveToolNames(),
    responses(steps = []) {
      const all = [...steps, ...Array.from({ length: 32 }, (_, n) => say(`fallback acknowledgement ${n}`))];
      faux.setResponses(all.map((step) => async (context, opts, state, model) => {
        requests.push(structuredClone({ ...context, tools: context.tools?.map(({ name, description, parameters }) => ({ name, description, parameters })) }));
        return typeof step === "function" ? step(context, opts, state, model) : step;
      }));
    },
    async prompt(steps, text = "inspect", source = "rpc") {
      live.responses(steps);
      await session.prompt(text, { source });
      await session.agent.waitForIdle();
    },
    controls: () => sessionManager.getEntries().filter((e) => e.type === "custom" && e.customType === "plan-control-result").map((e) => e.data),
    approved: () => sessionManager.getEntries().filter((e) => e.type === "custom_message" && e.customType === "plan-approved"),
    async control(command, source = "rpc") {
      const before = live.controls().length;
      await session.prompt(`/plan-control ${command}`, { source });
      const found = live.controls();
      if (found.length !== before + 1) throw new Error(`Expected one plan-control-result for ${command}; got ${found.length - before}`);
      return found.at(-1);
    },
    async state() { return (await live.control("status")).state; },
    async submit(steps) {
      const id = randomUUID();
      await live.prompt([call("plan_submit", { steps }, id), say("Draft ready")]);
      const event = events.find((e) => e.type === "tool_execution_end" && e.toolCallId === id);
      if (!event) throw new Error("plan_submit did not settle");
      return event;
    },
    async close(remove = true) {
      gate.resolve();
      for (const dialog of dialogs) dialog.answer.resolve(undefined);
      await session.abort();
      await session.agent.waitForIdle();
      session.dispose();
      if (remove) rmSync(box.root, { recursive: true, force: true });
    }
  };
  live.responses();
  return live;
}
export const approveArgs = (state) => `approve ${state.sessionId} ${state.planId} ${state.revision}`;
export function controlState(result) {
  if (!result.ok) throw new Error(`Control failed: ${JSON.stringify(result)}`);
  return result.state;
}
