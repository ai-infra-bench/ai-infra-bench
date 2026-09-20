#!/usr/bin/env node
// Independent oracle challenge (curator-only). Drives a real pi AgentSession with
// the faux provider against a candidate extension and checks contract-valid cases
// that are NOT copied from the verifier suites:
//
//   1. bg_run with a relative cwd, a Unicode error pattern and non-ASCII output:
//      the record's cwd is the resolved absolute path, the error wake carries the
//      exact UTF-8 line, and the exit wake follows with the exit code.
//   2. bash with intermittent output (a line every 400 ms for ~2.6 s) and
//      stalledSec 1: the silence timer must restart on every output, so the
//      command is NOT moved to the background and returns its full text.
//   3. bg_logs with an offset past the end returns an empty page whose offset and
//      total are consistent; bg_kill on an already-finished process returns the
//      final record unchanged with cleanup null and does not wake the agent again.
//
// Usage: node independent_probe.mjs <out.json>   (run inside the task image, cwd
// = /workspace/pi/packages/coding-agent, extension loaded from dist).
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import {
	createAgentSession,
	DefaultResourceLoader,
	SessionManager,
	SettingsManager,
} from "@earendil-works/pi-coding-agent";

const outFile = process.argv[2];
const root = mkdtempSync(join(tmpdir(), "bg-independent-"));
const cwd = join(root, "project");
const agentDir = join(root, "agent");
const sessionDir = join(root, "sessions");
for (const dir of [cwd, agentDir, sessionDir, join(cwd, "sub", "dir")]) mkdirSync(dir, { recursive: true });

const faux = fauxProvider({
	provider: "probe",
	api: "probe-api",
	models: [{ id: "probe-model", contextWindow: 100_000, maxTokens: 2_048 }],
});
const settingsManager = SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
const extensionPath = join(process.cwd(), "examples/extensions/background-processes/index.ts");
const loader = new DefaultResourceLoader({
	cwd,
	agentDir,
	settingsManager,
	additionalExtensionPaths: [extensionPath],
	extensionFactories: [{ name: "faux", factory: (pi) => pi.registerProvider(faux.provider) }],
	noExtensions: true,
	noSkills: true,
	noPromptTemplates: true,
	noThemes: true,
	noContextFiles: true,
});
await loader.reload();
const { session } = await createAgentSession({
	cwd,
	agentDir,
	model: faux.getModel(),
	thinkingLevel: "off",
	noTools: "builtin",
	resourceLoader: loader,
	sessionManager: SessionManager.create(cwd, sessionDir),
	settingsManager,
});
await session.bindExtensions({});

const results = [];
session.subscribe((event) => {
	if (event.type === "tool_execution_end") results.push(event);
});
const toolCall = (name, args) => fauxAssistantMessage(fauxToolCall(name, args), { stopReason: "toolUse" });
const say = (text) => fauxAssistantMessage(fauxText(text));
const acks = () => [say("ack 1"), say("ack 2"), say("ack 3"), say("ack 4")];
async function prompt(steps, text = "go") {
	faux.setResponses([...steps, ...acks()]);
	await session.prompt(text, { expandPromptTemplates: false, source: "interactive" });
}
const last = (name) => results.filter((r) => r.toolName === name).at(-1);
const details = (r) =>
	r.result?.details && typeof r.result.details === "object"
		? r.result.details
		: JSON.parse(r.result.content.map((b) => b.text ?? "").join("\n"));
const text = (r) => r.result.content.map((b) => b.text ?? "").join("\n");
const wakes = () =>
	session.messages.filter((m) => m.role === "custom" && m.customType === "background-process").map((m) => m.details);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(probe, ms, label) {
	const deadline = Date.now() + ms;
	while (!probe()) {
		if (Date.now() > deadline) throw new Error(`timed out: ${label}`);
		await sleep(25);
	}
	return probe();
}
const checks = {};
const record = (name, ok, info) => {
	checks[name] = { ok: Boolean(ok), ...(info ?? {}) };
};

// ---- case 1: relative cwd, Unicode error pattern, non-ASCII lines --------------------
const node = JSON.stringify(process.execPath);
const script1 =
	"console.log('准备中 … ok'); setTimeout(() => { console.log('警告：磁盘空间不足 ⚠'); }, 150); setTimeout(() => process.exit(5), 700);";
await prompt([
	toolCall("bg_run", {
		command: `${node} -e ${JSON.stringify(script1)}`,
		cwd: "sub/dir",
		name: "unicode",
		wake: { error: "^警告" },
	}),
	say("started"),
]);
const rec1 = details(last("bg_run"));
record("relative_cwd_resolved", rec1.cwd === join(cwd, "sub", "dir") && rec1.state === "running", { cwd: rec1.cwd });
await waitFor(() => wakes().some((w) => w.reasons.includes("exit")), 6000, "unicode exit wake");
await waitFor(() => !session.isStreaming, 6000, "settled after unicode wakes");
const w1 = wakes().filter((w) => w.id === rec1.id);
const errorWake = w1.find((w) => w.reasons.includes("error"));
const exitWake = w1.find((w) => w.reasons.includes("exit"));
record("unicode_error_line_exact", errorWake && errorWake.matchedLine === "警告：磁盘空间不足 ⚠", {
	matchedLine: errorWake?.matchedLine ?? null,
});
record(
	"exit_after_error_with_code",
	exitWake && exitWake.exitCode === 5 && w1.filter((w) => w.reasons.includes("exit")).length === 1,
	{ exitCode: exitWake?.exitCode ?? null, wakes: w1.map((w) => w.reasons) },
);
await prompt([toolCall("bg_logs", { id: rec1.id, offset: 0 }), say("logs")]);
const logs1 = details(last("bg_logs"));
record("utf8_lines_in_log", logs1.lines[0] === "准备中 … ok" && logs1.lines.includes("警告：磁盘空间不足 ⚠"), {
	lines: logs1.lines.slice(0, 3),
});

// ---- case 2: intermittent output must keep a bash command in the foreground -----------
const script2 =
	"let n = 0; const t = setInterval(() => { n += 1; console.log('tick ' + n); if (n === 6) { clearInterval(t); } }, 400);";
const wakesBefore = wakes().length;
const t0 = Date.now();
await prompt([
	toolCall("bash", { command: `${node} -e ${JSON.stringify(script2)}`, stalledSec: 1, timeout: 10 }),
	say("bash done"),
]);
const bashCall = last("bash");
const elapsed = Date.now() - t0;
let bashBackgrounded = false;
try {
	bashBackgrounded = details(bashCall).backgrounded === true;
} catch {
	bashBackgrounded = false;
}
record(
	"intermittent_output_stays_foreground",
	!bashCall.isError &&
		!bashBackgrounded &&
		text(bashCall).includes("tick 1") &&
		text(bashCall).includes("tick 6") &&
		elapsed >= 2300 &&
		elapsed < 9000,
	{ elapsedMs: elapsed, isError: bashCall.isError, backgrounded: bashBackgrounded },
);
await sleep(300);
record("no_wake_for_foreground_command", wakes().length === wakesBefore, { wakes: wakes().length - wakesBefore });

// ---- case 3: paging past the end; bg_kill on a finished process ----------------------
await prompt([toolCall("bg_logs", { id: rec1.id, offset: 100000, limit: 5 }), say("past end")]);
const past = details(last("bg_logs"));
// The contract fixes the shape ({id, offset, lines, total}) and that a page never
// exceeds the log; whether `offset` echoes the request or clamps to `total` is left open.
record(
	"logs_offset_past_end",
	Array.isArray(past.lines) &&
		past.lines.length === 0 &&
		Number.isInteger(past.offset) &&
		past.total >= 2 &&
		past.id === rec1.id,
	{ offset: past.offset, total: past.total },
);
const wakesBeforeKill = wakes().length;
await prompt([toolCall("bg_kill", { id: rec1.id, timeoutSec: 1 }), say("killed?")]);
const killed = details(last("bg_kill"));
await sleep(400);
record(
	"kill_finished_process_is_noop",
	killed.state === "exited" &&
		killed.exitCode === 5 &&
		(killed.cleanup === null || killed.cleanup === undefined) &&
		wakes().length === wakesBeforeKill,
	{ state: killed.state, exitCode: killed.exitCode, cleanup: killed.cleanup ?? null },
);

const passed = Object.values(checks).every((c) => c.ok);
writeFileSync(outFile, `${JSON.stringify({ passed, checks, sessionFile: session.sessionFile }, null, 2)}\n`);
console.log(JSON.stringify({ passed, checks }, null, 2));
session.dispose();
process.exit(passed ? 0 : 1);
