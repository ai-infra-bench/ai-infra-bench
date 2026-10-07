/** Independent Node process. Only the real SDK loads the candidate extension. */
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { start, approveArgs, call, say, waitFor } from "../plan_support.mjs";
const config = JSON.parse(readFileSync(process.argv[2], "utf8"));
const { mode, outFile, box } = config;
const original = ["grep", "write", "verifier_effect"];
if (mode === "seed-without-extension") {
  const { DefaultResourceLoader, SettingsManager, SessionManager, createAgentSession } = await import("@earendil-works/pi-coding-agent");
  const { fauxProvider, fauxAssistantMessage } = await import("@earendil-works/pi-ai/providers/faux");
  const faux = fauxProvider({ provider: "normal-seed", api: "normal-seed-api", models: [{ id: "seed", contextWindow: 20000, maxTokens: 1000 }] });
  const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const resourceLoader = new DefaultResourceLoader({ cwd: box.cwd, agentDir: box.agentDir, settingsManager,
    noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    extensionFactories: [{ name: "seed-provider", factory: (pi) => pi.registerProvider(faux.provider) }] });
  await resourceLoader.reload();
  const sessionManager = SessionManager.create(box.cwd, box.sessionDir);
  const { session } = await createAgentSession({ cwd: box.cwd, agentDir: box.agentDir, model: faux.getModel(), resourceLoader, sessionManager, settingsManager, thinkingLevel: "off" });
  await session.bindExtensions({ mode: "rpc" });
  faux.setResponses([fauxAssistantMessage("An ordinary assistant reply before Plan Mode was enabled.")]);
  await session.prompt("Explain the repository", { source: "rpc" });
  await session.agent.waitForIdle();
  const result = { pid: process.pid, sessionFile: session.sessionFile, sessionId: sessionManager.getSessionId(),
    entries: sessionManager.getEntries(), calls: faux.state.callCount, errors: [] };
  await session.extensionRunner.emit({ type: "session_shutdown", reason: "quit" });
  session.dispose();
  writeFileSync(outFile, JSON.stringify(result));
} else {
const live = await start({ box, sessionFile: config.sessionFile, activeTools: mode.startsWith("seed") ? original : undefined,
  flag: config.flag, seedEntries: config.seedEntries });
try {
  const callsAtOpen = live.faux.state.callCount;
  if (mode.startsWith("seed")) {
    // Pi only publishes normal file-backed sessions after an assistant reply.
    await live.prompt([say("persisted assistant baseline")], "establish session");
    if (mode !== "seed-normal") {
    const entered = await live.control("enter"); if (!entered.ok) throw new Error(JSON.stringify(entered));
    const submitted = await live.submit(["  persistent step Ω  ", "check\nexact strings"]);
    if (submitted.isError) throw new Error(JSON.stringify(submitted));
    if (mode === "seed-approved") {
      const draft = await live.state();
      live.responses([call("verifier_effect", { path: join(box.cwd, "executions.txt"), marker: "once" }), say("executed")]);
      const approval = await live.control(approveArgs(draft)); if (!approval.ok) throw new Error(JSON.stringify(approval));
      await waitFor(() => existsSync(join(box.cwd, "executions.txt")) && live.session.isIdle, "seed approval execution");
    }
    }
  }
  const state = await live.state();
  const beforeReplayProbe = live.faux.state.callCount;
  // Explicit status has no model turn. Allow queued microtasks and a short bounded
  // host turn so immediate auto-replay cannot hide behind child process exit.
  await new Promise((resolve) => setTimeout(resolve, 150));
  const result = { pid: process.pid, state, tools: live.tools(), callsAtOpen,
    beforeReplayProbe, calls: live.faux.state.callCount, approvedCount: live.approved().length,
    sessionFile: live.session.sessionFile, entries: live.sessionManager.getEntries(), errors: live.errors,
    executions: existsSync(join(box.cwd, "executions.txt")) ? readFileSync(join(box.cwd, "executions.txt"), "utf8") : "" };
  if (mode === "resume-and-approve") {
    live.responses([call("verifier_effect", { path: join(box.cwd, "executions.txt"), marker: "once" }), say("executed")]);
    result.approval = await live.control(approveArgs(state));
    await waitFor(() => existsSync(join(box.cwd, "executions.txt")) && live.session.isIdle, "resumed approval executes");
    result.afterState = await live.state(); result.afterTools = live.tools();
    result.executions = readFileSync(join(box.cwd, "executions.txt"), "utf8");
  }
  if (!live.session.isIdle) throw new Error("Normal lifecycle fixture may close only while idle");
  await live.close(false);
  writeFileSync(outFile, JSON.stringify(result));
} catch (error) { await live.close(false); throw error; }

}
