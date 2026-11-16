/** Verifier host: real SDK, resource loader, faux provider and file-backed sessions. */
import { mkdtempSync, mkdirSync, rmSync, writeFileSync, appendFileSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import { stripVTControlCharacters } from "node:util";
import { Type } from "typebox";
import xterm from "@xterm/headless";
import { Container, Text, TuiMainScreen } from "@earendil-works/pi-tui";
import { fauxProvider, fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSession, CustomMessageComponent, DefaultResourceLoader, SessionManager, SettingsManager, initTheme } from "@earendil-works/pi-coding-agent";

// The host supplies Pi's real keybinding object; the package exports its type only.
import { KeybindingsManager } from "../../src/core/keybindings.ts";
import { ToolExecutionComponent } from "../../src/modes/interactive/components/tool-execution.ts";

import { ExtensionSelectorComponent } from "../../src/modes/interactive/components/extension-selector.ts";
import { navigateReview, readReview } from "./ui_review_driver.mjs";

export const WORKSPACE = process.env.PI_WORKSPACE ?? "/workspace/pi";
export const EXTENSION = join(WORKSPACE, "packages/coding-agent/examples/extensions/plan-mode/index.ts");
export const DEFAULT_TOOLS = ["read", "write", "bash", "edit", "grep", "find", "ls", "verifier_effect", "verifier_wait"];
export const say = (text) => fauxAssistantMessage(text);
export const call = (name, args, id = randomUUID()) => fauxAssistantMessage(fauxToolCall(name, args, { id }), { stopReason: "toolUse" });
export const textOf = (message) => typeof message.content === "string" ? message.content : (message.content ?? []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
export function planState(state) {
  const fields = ["sessionId", "mode", "planId", "revision", "steps"];
  if (!state || typeof state !== "object" || Array.isArray(state) || fields.some((field) => !Object.hasOwn(state, field))) {
    throw new Error("Plan state must expose sessionId, mode, planId, revision and steps");
  }
  if (typeof state.sessionId !== "string" || !state.sessionId.length || !["normal", "planning", "approved"].includes(state.mode) ||
      !Array.isArray(state.steps) || state.steps.some((step) => typeof step !== "string")) {
    throw new Error(`Invalid public plan state: ${JSON.stringify(state)}`);
  }
  // An inactive state's identity/revision sentinels are presentation choices.
  if (state.mode === "normal" ? state.steps.length !== 0 :
      typeof state.planId !== "string" || !state.planId.length || typeof state.revision !== "number" || !Number.isFinite(state.revision)) {
    throw new Error(`Invalid active plan identity or normal draft: ${JSON.stringify(state)}`);
  }
  return Object.fromEntries(fields.map((field) => [field, state[field]]));
}
export function submittedStates(result) {
  const candidates = [result.details];
  const texts = [textOf(result), ...(Array.isArray(result.content) ? result.content.filter((block) => block.type === "text").map((block) => block.text) : [])];
  for (const text of texts) { try { candidates.push(JSON.parse(text)); } catch {} }
  // One structured channel is sufficient; both need not duplicate the state.
  return candidates.flatMap((value) => [value, value?.state]).flatMap((candidate) => { try { return [planState(candidate)]; } catch { return []; } });
}
function hasReason(value, seen = new Set()) {
  if (typeof value === "string") return value.trim().length > 0;
  if (!value || typeof value !== "object" || seen.has(value)) return false;
  seen.add(value);
  return Object.values(value).some((item) => hasReason(item, seen));
}
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
  const requests = [], events = [], errors = [], dialogs = [], notices = [], uiOutput = [];
  const showText = (text) => { if (typeof text === "string") uiOutput.push(stripVTControlCharacters(text)); };
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
  const baseUI = session.extensionRunner.getUIContext();
  // Only the physical terminal is substituted. Public widget factories receive
  // the real TUI and Theme, and their own components determine rendered text.
  let terminalInput;
  const screen = new xterm.Terminal({ cols: 120, rows: 40, allowProposedApi: true });
  let screenFlushed = Promise.resolve();
  const writeTerminal = (data) => {
    showText(data);
    screenFlushed = new Promise((resolve) => screen.write(data, resolve));
  };
  const terminal = {
    columns: 120, rows: 40, kittyProtocolActive: false,
    start(onInput) { terminalInput = onInput; }, stop() {}, async drainInput() {}, write: writeTerminal,
    moveBy() {}, hideCursor() {}, showCursor() {}, clearLine() {},
    clearFromCursor() {}, clearScreen() {}, setTitle() {}, setProgress() {},
  };
  const widgetTui = new TuiMainScreen(terminal);
  const widgets = new Map(), surfaces = [], terminalSubscriptions = new Set();
  const editorComponent = new Text("", 0, 0);
  widgetTui.addChild(editorComponent);
  widgetTui.setFocus(editorComponent);
  widgetTui.start();
  let editorText = "", closing = false, autoChoosing = false;
  const pause = () => new Promise((resolve) => setTimeout(resolve, 0));
  function surfaceFor(component, active, width = () => terminal.columns, height = () => terminal.rows, bounds = () => undefined) {
    const surface = {
      read() {
        widgetTui.renderNow(true);
        if (!active()) return undefined;
        const observed = readReview(component.render(width()));
        if (!observed) return undefined;
        // Confirm the selected line on the actual composed terminal viewport.
        // Component output alone is insufficient: it may be clipped, covered,
        // hidden, or outside the screen. xterm interprets cursor movement and
        // erasures, so old transcript output is never used as current UI.
        const rectangle = bounds();
        const viewport = Array.from({ length: rectangle?.height ?? screen.rows }, (_, n) => {
          const row = screen.buffer.active.viewportY + (rectangle?.row ?? 0) + n;
          return screen.buffer.active.getLine(row)?.translateToString(true, rectangle?.col ?? 0,
            rectangle ? rectangle.col + rectangle.width : screen.cols) ?? "";
        });
        if (!viewport.some((line) => line.trim() === observed.selectionLine.trim())) return undefined;
        const componentLines = new Set(observed.text.split("\n").map((line) => line.trim()));
        const visibleLines = viewport.filter((line) => componentLines.has(line.trim()));
        return { ...observed, text: visibleLines.join("\n") };
      },
      async key(key) {
        if (!active()) throw new Error("UI observer: refusing input to an inactive review");
        const before = surface.read();
        terminalInput(key);
        widgetTui.renderNow(true);
        await screenFlushed;
        await pause();
        if (key !== "\r") {
          // Rendering may be scheduled asynchronously by a custom component.
          // Wait under the same UI timeout used to open a review. An unchanged
          // selection at that limit is a clamp boundary, not an assumed sync
          // update. The navigation driver will try the opposite direction.
          const until = Date.now() + 6000;
          while (Date.now() < until && active()) {
            await screenFlushed;
            const after = surface.read();
            if (after && after.selected !== before?.selected) break;
            await new Promise((resolve) => setTimeout(resolve, 10));
          }
        }
      },
      async choose(kind, checkpoint) {
        await navigateReview(surface, kind, checkpoint);
        await surface.key("\r");
      },
    };
    surfaces.push(surface);
    return surface;
  }
  function setWidget(key, content) {
    const old = widgets.get(key);
    if (old) { old.component.dispose?.(); widgetTui.removeChild(old.component); widgets.delete(key); }
    if (content !== undefined) {
      let component;
      if (Array.isArray(content)) {
        component = new Container();
        for (const line of content) component.addChild(new Text(line, 1, 0));
      } else component = content(widgetTui, baseUI.theme);
      const entry = { component };
      widgets.set(key, entry); widgetTui.addChild(component);
      // Updating one public widget slot is a redraw, not a new dialog. Keep
      // navigation on that slot while its candidate component is replaced.
      entry.surface = old?.surface ?? surfaceFor({ render: (width) => widgets.get(key)?.component.render(width) ?? [] },
        () => widgets.has(key) && !widgetTui.hasOverlay() && widgetTui.getFocusedComponent() === editorComponent);
    }
    widgetTui.renderNow(true);
  }
  let modal;
  function attachDialog(component, answer, cleanup, displayOptions = {}) {
    let settled = false, overlay;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      cleanup?.();
      if (overlay) overlay.hide();
      else if (modal?.component === component) {
        widgetTui.removeChild(component); modal = undefined; widgetTui.setFocus(editorComponent);
      }
      component.dispose?.(); widgetTui.renderNow(true); answer.resolve(value);
    };
    if (displayOptions.overlay) {
      overlay = widgetTui.showOverlay(component, typeof displayOptions.overlayOptions === "function" ? displayOptions.overlayOptions() : displayOptions.overlayOptions);
      displayOptions.onHandle?.(overlay);
    } else {
      if (modal) { widgetTui.removeChild(modal.component); modal.component.dispose?.(); }
      modal = { component }; widgetTui.addChild(component); widgetTui.setFocus(component);
    }
    const surface = surfaceFor(component,
      () => !settled && (overlay ? !overlay.isHidden() && overlay.isFocused() : modal?.component === component && !widgetTui.hasOverlay() && widgetTui.getFocusedComponent() === component),
      () => overlay?.getBounds()?.width ?? terminal.columns,
      () => overlay?.getBounds()?.height ?? terminal.rows,
      () => overlay?.getBounds());
    const dialog = { ...surface, cancel: () => finish(undefined), answer };
    dialogs.push(dialog);
    widgetTui.renderNow(true);
    return { finish, dialog };
  }
  const ui = { ...baseUI,
    notify: (message, type) => { notices.push({ message, type }); showText(message); },
    setStatus: (_key, text) => showText(text),
    setWidget,
    onTerminalInput(handler) {
      const unsubscribe = widgetTui.addInputListener(handler);
      terminalSubscriptions.add(unsubscribe);
      return () => { unsubscribe(); terminalSubscriptions.delete(unsubscribe); };
    },
    setEditorText(text) { editorText = text; },
    getEditorText: () => editorText,
    select: async (title, choices, opts = {}) => {
      if (opts.signal?.aborted) return undefined;
      const answer = deferred();
      let host;
      const component = new ExtensionSelectorComponent(title, choices,
        (choice) => host.finish(choice), () => host.finish(undefined), { tui: widgetTui, timeout: opts.timeout });
      const abort = () => host.finish(undefined);
      host = attachDialog(component, answer, () => opts.signal?.removeEventListener("abort", abort));
      opts.signal?.addEventListener("abort", abort, { once: true });
      return answer.promise;
    },
    custom: async (factory, displayOptions = {}) => {
      const answer = deferred();
      let host, early = false, earlyValue;
      const component = await factory(widgetTui, baseUI.theme, new KeybindingsManager(), (value) => {
        if (host) host.finish(value); else { early = true; earlyValue = value; }
      });
      if (early) { component?.dispose?.(); return earlyValue; }
      host = attachDialog(component, answer, undefined, displayOptions);
      return answer.promise;
    },
    input: async () => options.refinement ?? "Refine without executing",
    editor: async () => options.refinement ?? "Refine without executing",
  };
  const activeReview = () => [...surfaces].reverse().find((surface) => surface.read());
  // Ordinary non-UI cases dismiss review through the same public keyboard
  // path; a candidate never receives a host-invented answer string.
  const autoTimer = options.ui && !options.deferUI ? setInterval(async () => {
    if (closing || autoChoosing) return;
    const surface = activeReview();
    if (!surface) return;
    autoChoosing = true;
    try { await surface.choose("stay"); } catch (error) { errors.push(error); }
    finally { autoChoosing = false; }
  }, 10) : undefined;
  const renderedTools = new Map();
  session.subscribe((event) => {
    events.push(event);
    if (options.ui && event.type === "tool_execution_start" && event.toolName === "plan_submit") {
      // This is the same public tool renderer used by InteractiveMode. Structured
      // details alone are not visible; a custom renderer may deliberately hide them.
      const component = new ToolExecutionComponent(event.toolName, event.toolCallId, event.args,
        { showImages: false }, session.getToolDefinition(event.toolName), widgetTui, box.cwd);
      component.setArgsComplete();
      component.markExecutionStarted();
      renderedTools.set(event.toolCallId, component);
    }
    if (options.ui && event.type === "tool_execution_end" && event.toolName === "plan_submit") {
      const component = renderedTools.get(event.toolCallId);
      if (!component) throw new Error("Missing tool execution renderer");
      component.updateResult({ ...event.result, isError: event.isError });
      // Readers can expand tool output before approval, including while the
      // extension selector is open. Honor the actual renderer in that state.
      component.setExpanded(true);
      // Wrapped terminal rows remain visible to a reader as one flow of text.
      showText(component.render(terminal.columns).map(stripVTControlCharacters).map((line) => line.trim()).join(" "));
      renderedTools.delete(event.toolCallId);
    }
    if (options.ui && event.type === "message_start" && event.message.role === "custom" && event.message.display) {
      // Pi displays these transcript messages independently of ctx.ui methods.
      // Run the real renderer, including a candidate's registered renderer;
      // hidden messages and structured details are not display evidence.
      const component = new CustomMessageComponent(event.message, session.extensionRunner.getMessageRenderer(event.message.customType));
      component.render(terminal.columns).forEach(showText);
    }
  });
  const bind = { mode: options.ui ? "tui" : "rpc", onError: (error) => errors.push(error) };
  if (options.ui) bind.uiContext = ui;
  await session.bindExtensions(bind);
  const live = { box, session, sessionManager, faux, requests, events, errors, dialogs, notices, uiOutput, api, activeReview,
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
    async control(command, source = "rpc", options = {}) {
      const before = live.controls().length;
      await session.prompt(`/plan-control ${command}`, { source });
      const operation = command.trim().split(/\s+/)[0];
      const found = live.controls().slice(before);
      if (found.length !== 1) throw new Error(`Expected one plan-control-result for ${command}; got ${found.length}`);
      const result = found.at(-1);
      if (!result || typeof result !== "object" || typeof result.operation !== "string" || !result.operation.trim() || typeof result.ok !== "boolean") {
        throw new Error(`Invalid control result: ${JSON.stringify(result)}`);
      }
      if (!options.malformed && ["enter", "status", "approve"].includes(operation) && result.operation !== operation) {
        throw new Error(`Control result does not identify ${operation}: ${JSON.stringify(result)}`);
      }
      const state = planState(result.state);
      if (state.sessionId !== sessionManager.getSessionId()) throw new Error("Control state does not identify the current Pi session");
      const metadata = Object.fromEntries(Object.entries(result).filter(([key]) => !["operation", "ok", "state"].includes(key)));
      if (!result.ok && !hasReason(metadata)) throw new Error(`Rejected control has no reason: ${JSON.stringify(result)}`);
      return { ...result, state };
    },
    async state() { return controlState(await live.control("status")); },
    async submit(steps) {
      const id = randomUUID();
      await live.prompt([call("plan_submit", { steps }, id), say("Draft ready")]);
      const event = events.find((e) => e.type === "tool_execution_end" && e.toolCallId === id);
      if (!event) throw new Error("plan_submit did not settle");
      return event;
    },
    async close(remove = true) {
      closing = true; clearInterval(autoTimer);
      gate.resolve();
      for (const dialog of dialogs) { if (dialog.cancel) dialog.cancel(); else dialog.answer.resolve(undefined); }
      await session.abort();
      await session.agent.waitForIdle();
      await session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
      session.dispose();
      for (const widget of widgets.values()) widget.component.dispose?.();
      for (const unsubscribe of terminalSubscriptions) unsubscribe();
      widgets.clear(); widgetTui.clear(); widgetTui.stop();
      await screenFlushed; screen.dispose();
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
