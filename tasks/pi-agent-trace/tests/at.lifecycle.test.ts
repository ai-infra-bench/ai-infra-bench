/**
 * Durability across pi processes: a later process continues the same trace.
 * Each case spawns real child pi processes built from the published package
 * entry points.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeAll, expect, it } from "vitest";
import {
	FIXTURES,
	liveProblems,
	named,
	readTrace,
	type Sandbox,
	sandbox,
	sleep,
	traceProblems,
	WORKSPACE,
	waitFor,
} from "./at_support.ts";

const CHILD_DIR = join(WORKSPACE, "packages/coding-agent/test/__verifier__");
const CHILD = join(CHILD_DIR, "pi_child.mjs");

beforeAll(() => {
	mkdirSync(CHILD_DIR, { recursive: true });
	copyFileSync(join(FIXTURES, "pi_child.mjs"), CHILD);
});
const boxes: Sandbox[] = [];
const children: ChildProcess[] = [];

afterEach(async () => {
	for (const child of children.splice(0)) {
		if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
	}
	for (const box of boxes.splice(0)) box.cleanup();
});

function childEnv() {
	return {
		...process.env,
		PI_WORKSPACE: WORKSPACE,
		PI_VERIFIER_FIXTURES: FIXTURES,
		PI_OFFLINE: "1",
		PI_TELEMETRY: "0",
		PI_NO_LOCAL_LLM: "1",
		NODE_OPTIONS: "",
	};
}

function spawnChild(args: string[]): ChildProcess {
	const child = spawn(process.execPath, [CHILD, ...args], {
		cwd: join(WORKSPACE, "packages/coding-agent"),
		env: childEnv(),
		stdio: ["ignore", "pipe", "pipe"],
	});
	let output = "";
	const collect = (chunk: Buffer | string) => {
		output += chunk;
	};
	child.stdout?.on("data", collect);
	child.stderr?.on("data", collect);
	(child as any).output = () => output;
	children.push(child);
	return child;
}

function exited(child: ChildProcess): Promise<{ code: number | null; signal: NodeJS.Signals | null }> {
	if (child.exitCode !== null || child.signalCode !== null) {
		return Promise.resolve({ code: child.exitCode, signal: child.signalCode });
	}
	return new Promise((resolve) => child.once("exit", (code, signal) => resolve({ code, signal })));
}

async function readJson(file: string, child: ChildProcess): Promise<any> {
	await waitFor(() => existsSync(file) || child.exitCode !== null || child.signalCode !== null, {
		label: `child output ${file}`,
		timeoutMs: 30000,
	});
	if (!existsSync(file)) {
		throw new Error(
			`child exited (code ${child.exitCode}, signal ${child.signalCode}) before writing ${file}:\n${(child as any).output()}`,
		);
	}
	return JSON.parse(readFileSync(file, "utf8"));
}

async function runChild(box: Sandbox, mode: string, target: string, name: string) {
	const out = join(box.root, name);
	const child = spawnChild([mode, target, box.cwd, box.agentDir, out]);
	const view = await readJson(out, child);
	expect((await exited(child)).code, (child as any).output()).toBe(0);
	await sleep(100);
	return view;
}

/** The branch as the verifier sees it, in the shape traceProblems expects. */
function branchEntries(view: any) {
	return view.branch.map((e: any) =>
		e.type === "message"
			? {
					id: e.id,
					type: "message",
					message: e.role === "toolResult" ? { role: e.role, toolCallId: e.toolCallId } : { role: e.role },
				}
			: { id: e.id, type: e.type, tokensBefore: e.tokensBefore },
	);
}

it("a later pi process appends to the same trace with the same trace id and its own process id", async () => {
	const box = sandbox();
	boxes.push(box);
	const first = await runChild(box, "build", box.sessionDir, "build.json");
	const file = join(first.sessionDir, "traces", `${first.sessionId}.otlp.jsonl`);
	const before = readTrace(file);
	expect(traceProblems(before.spans, before.errors, branchEntries(first), first.sessionId)).toEqual([]);
	expect(liveProblems(before.all)).toEqual([]);
	expect(named(before.spans, "pi.run")).toHaveLength(2);
	expect(named(before.spans, "pi.compaction")).toHaveLength(1);
	expect(named(before.spans, "execute_tool")).toHaveLength(1);
	for (const span of before.spans) expect(span.resource["process.pid"]).toBe(first.pid);

	const second = await runChild(box, "resume", first.sessionFile, "resume.json");
	expect(second.sessionId).toBe(first.sessionId);
	expect(second.pid).not.toBe(first.pid);
	const after = readTrace(file);
	expect(traceProblems(after.spans, after.errors, branchEntries(second), second.sessionId)).toEqual([]);
	expect(liveProblems(after.all)).toEqual([]);
	// Everything the first process wrote is untouched; the second process appended its own run.
	expect(after.spans.slice(0, before.spans.length).map((s) => s.spanId)).toEqual(before.spans.map((s) => s.spanId));
	const added = after.spans.slice(before.spans.length);
	expect(added.map((s) => s.name)).toEqual([
		"chat at-child-model",
		"execute_tool echo",
		"pi.turn",
		"chat at-child-model",
		"pi.turn",
		"pi.run",
	]);
	for (const span of added) {
		expect(span.resource["process.pid"]).toBe(second.pid);
		expect(span.traceId).toBe(before.spans[0].traceId);
	}
	expect(new Set(after.spans.map((s) => s.spanId)).size).toBe(after.spans.length);
});

it("a pi process killed during a tool execution leaves that turn's chat span on disk", async () => {
	const box = sandbox();
	boxes.push(box);
	const first = await runChild(box, "build", box.sessionDir, "build.json");
	const file = join(first.sessionDir, "traces", `${first.sessionId}.otlp.jsonl`);
	const before = readTrace(file);
	expect(before.errors).toEqual([]);

	const marker = join(box.root, "slow.marker");
	const child = spawnChild([
		"slow-tool",
		first.sessionFile,
		box.cwd,
		box.agentDir,
		join(box.root, "unused.json"),
		marker,
	]);
	await waitFor(() => existsSync(marker), { label: "slow tool started", timeoutMs: 30000 });
	await sleep(200);
	child.kill("SIGKILL");
	const exit = await exited(child);
	expect(exit.signal).toBe("SIGKILL");

	const after = readTrace(file);
	expect(after.errors).toEqual([]);
	expect(after.spans.slice(0, before.spans.length).map((s) => s.spanId)).toEqual(before.spans.map((s) => s.spanId));
	const added = after.spans.slice(before.spans.length);
	// Only the chat span of the interrupted turn ended; the run, the turn and the tool left start lines only.
	expect(added.map((s) => s.name)).toEqual(["chat at-child-model"]);
	const addedStarts = after.starts.slice(before.starts.length);
	expect(addedStarts.map((s) => s.name)).toEqual(["pi.run", "pi.turn", "chat at-child-model", "execute_tool echo"]);
	expect(liveProblems(after.all)).toEqual([]);
	expect(added[0].parentSpanId).toBe(addedStarts[1].spanId);
	const session = readFileSync(first.sessionFile, "utf8")
		.split("\n")
		.filter(Boolean)
		.map((line) => JSON.parse(line));
	const assistants = session.filter((e) => e.type === "message" && e.message?.role === "assistant");
	expect(added[0].attributes["pi.session.entry_id"]).toBe(assistants[assistants.length - 1].id);
	expect(added[0].attributes["gen_ai.response.finish_reasons"]).toEqual(["toolUse"]);
	expect(added[0].status).toEqual({ code: 1 });
	expect(after.spans.some((s) => s.spanId === added[0].parentSpanId)).toBe(false);

	// The file is intact: a later process appends normally.
	const third = await runChild(box, "resume", first.sessionFile, "resume.json");
	const final = readTrace(file);
	expect(final.errors).toEqual([]);
	expect(final.spans.slice(0, after.spans.length).map((s) => s.spanId)).toEqual(after.spans.map((s) => s.spanId));
	expect(final.spans.slice(after.spans.length).map((s) => s.name)).toEqual([
		"chat at-child-model",
		"execute_tool echo",
		"pi.turn",
		"chat at-child-model",
		"pi.turn",
		"pi.run",
	]);
	expect(third.pid).not.toBe(first.pid);
});
