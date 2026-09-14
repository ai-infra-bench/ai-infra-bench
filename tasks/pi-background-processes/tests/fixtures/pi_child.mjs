#!/usr/bin/env node
/**
 * A separate pi OS process driven by the verifier. Uses the published package
 * entry points (dist) exactly like an external SDK consumer would. The
 * lifecycle suite copies this file into the workspace before spawning it so
 * package resolution uses the workspace node_modules.
 *
 * Modes:
 *   start-and-exit  <sessionDir> <cwd> <agentDir> <out.json>   start a fixture with a SIGTERM-ignoring grandchild, write pids, exit normally
 *   start-and-wait  <sessionDir> <cwd> <agentDir> <out.json>   same, but stay alive until this process receives SIGTERM
 *   run-to-exit     <sessionDir> <cwd> <agentDir> <out.json>   run a fixture to completion (exit code 7), wait for the exit wake, exit
 *   resume-read     <sessionFile> <cwd> <agentDir> <out.json> <id>   open the session file in a fresh process and read the finished record + logs
 */
import { writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";

const [mode, target, cwd, agentDir, outFile, extra] = process.argv.slice(2);
const workspace = process.env.PI_WORKSPACE ?? "/workspace/pi";
const extensionPath = join(workspace, "packages/coding-agent/examples/extensions/background-processes/index.ts");
const emit = join(process.env.PI_VERIFIER_FIXTURES ?? "/tests/fixtures", "emit.mjs");

const faux = fauxProvider({
	provider: "bg-child",
	api: "bg-child-api",
	models: [{ id: "bg-child-model", contextWindow: 200_000, maxTokens: 8_192 }],
});
const toolCall = (name, args) => fauxAssistantMessage(fauxToolCall(name, args), { stopReason: "toolUse" });
const say = (text) => fauxAssistantMessage(fauxText(text));
const acks = Array.from({ length: 6 }, (_, i) => say(`ack ${i + 1}`));

const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
const loader = new DefaultResourceLoader({
	cwd,
	agentDir,
	settingsManager,
	additionalExtensionPaths: existsSync(extensionPath) ? [extensionPath] : [],
	extensionFactories: [{ name: "bg-child-faux", factory: (pi) => pi.registerProvider(faux.provider) }],
	noExtensions: true,
	noSkills: true,
	noPromptTemplates: true,
	noThemes: true,
	noContextFiles: true,
	systemPrompt: "Deterministic child session.",
});
await loader.reload();

const sessionManager = mode === "resume-read" ? SessionManager.open(target, dirname(target)) : SessionManager.create(cwd, target);
const { session } = await createAgentSession({
	cwd,
	agentDir,
	model: faux.getModel(),
	thinkingLevel: "off",
	noTools: "builtin",
	resourceLoader: loader,
	sessionManager,
	settingsManager,
});

await session.bindExtensions({});
const results = [];
session.subscribe((event) => {
	if (event.type === "tool_execution_end") results.push({ toolName: event.toolName, result: event.result, isError: event.isError });
});
const payload = (toolName) => {
	const hit = [...results].reverse().find((r) => r.toolName === toolName);
	if (!hit) throw new Error(`no result for ${toolName}`);
	if (hit.isError) throw new Error(`${toolName} errored: ${JSON.stringify(hit.result)}`);
	if (hit.result?.details && typeof hit.result.details === "object") return hit.result.details;
	return JSON.parse(hit.result.content.map((b) => b.text ?? "").join("\n"));
};
const wakes = () => session.messages.filter((m) => m.role === "custom" && m.customType === "background-process");
const waitFor = async (probe, timeoutMs = 8000) => {
	const deadline = Date.now() + timeoutMs;
	while (Date.now() < deadline) {
		const v = probe();
		if (v) return v;
		await new Promise((r) => setTimeout(r, 25));
	}
	throw new Error("timed out in child");
};
const prompt = async (steps, text = "go") => {
	faux.setResponses([...steps, ...acks]);
	await session.prompt(text, { expandPromptTemplates: false, source: "interactive" });
};

if (mode === "start-and-exit" || mode === "start-and-wait") {
	const pidfile = join(cwd, "child-proc.pid");
	const grandchildPidfile = join(cwd, "grandchild.pid");
	const command = `${JSON.stringify(process.execPath)} ${JSON.stringify(emit)} --ignore-sigterm --spawn-grandchild ${grandchildPidfile} --exit-after 60000 --pidfile ${pidfile}`;
	await prompt([toolCall("bg_run", { command, name: "daemon" }), say("started")]);
	const record = payload("bg_run");
	await waitFor(() => existsSync(pidfile) && existsSync(grandchildPidfile));
	writeFileSync(
		outFile,
		JSON.stringify({
			id: record.id,
			pid: Number(readFileSync(pidfile, "utf8")),
			grandchild: Number(readFileSync(grandchildPidfile, "utf8")),
			sessionFile: session.sessionFile,
		}),
	);
	if (mode === "start-and-exit") {
		session.dispose();
		process.exit(0);
	}
	setInterval(() => {}, 1 << 30);
} else if (mode === "run-to-exit") {
	const command = `${JSON.stringify(process.execPath)} ${JSON.stringify(emit)} --exit-after 150 --exit-code 7`;
	await prompt([toolCall("bg_run", { command, name: "short-job" }), say("started")]);
	const record = payload("bg_run");
	await waitFor(() => wakes().length === 1);
	await waitFor(() => !session.isStreaming);
	await new Promise((r) => setTimeout(r, 200));
	writeFileSync(outFile, JSON.stringify({ id: record.id, sessionFile: session.sessionFile }));
	session.dispose();
	process.exit(0);
} else if (mode === "resume-read") {
	const id = extra;
	await prompt([toolCall("bg_list", {}), toolCall("bg_logs", { id, offset: 0, limit: 50 }), say("read")]);
	const list = payload("bg_list");
	const logs = payload("bg_logs");
	writeFileSync(outFile, JSON.stringify({ list: list.processes ?? list, logs }));
	session.dispose();
	process.exit(0);
} else {
	throw new Error(`unknown mode ${mode}`);
}
