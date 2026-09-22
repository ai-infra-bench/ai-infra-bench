/**
 * OS-process lifecycle contract: what happens when the pi process itself goes
 * away, and what a later pi process can still see. Each case spawns real child
 * pi processes built from the published package entry points.
 */
import { type ChildProcess, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeAll, expect, it } from "vitest";
import {
	FIXTURES,
	killGroupQuietly,
	pidAlive,
	type Sandbox,
	sandbox,
	sleep,
	WORKSPACE,
	waitFor,
} from "./bg_support.ts";

// Copied into the workspace so the child resolves @earendil-works/* from the workspace node_modules.
const CHILD_DIR = join(WORKSPACE, "packages/coding-agent/test/__verifier__");
const CHILD = join(CHILD_DIR, "pi_child.mjs");

beforeAll(() => {
	mkdirSync(CHILD_DIR, { recursive: true });
	copyFileSync(join(FIXTURES, "pi_child.mjs"), CHILD);
});
const boxes: Sandbox[] = [];
const children: ChildProcess[] = [];
const pids: number[] = [];

afterEach(async () => {
	for (const child of children.splice(0)) {
		if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
	}
	for (const pid of pids.splice(0)) killGroupQuietly(pid);
	for (const box of boxes.splice(0)) box.cleanup();
});

function childEnv() {
	// The child is a real pi process, not a test: keep the runner's own variables (VITEST*) out of it.
	const inherited = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("VITEST")));
	return {
		...inherited,
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

/** Wait for the child's output file, but surface the child's own output if it dies first. */
async function readJson(file: string, child: ChildProcess): Promise<any> {
	await waitFor(() => existsSync(file) || child.exitCode !== null || child.signalCode !== null, {
		label: `child output ${file}`,
		timeoutMs: 20000,
	});
	if (!existsSync(file)) {
		throw new Error(
			`child exited (code ${child.exitCode}, signal ${child.signalCode}) before writing ${file}:\n${(child as any).output()}`,
		);
	}
	return JSON.parse(readFileSync(file, "utf8"));
}

function fresh(): Sandbox {
	const box = sandbox();
	boxes.push(box);
	return box;
}

it("pi process exit stops managed processes and their grandchildren", async () => {
	const box = fresh();
	const out = box.file("out.json");
	const child = spawnChild(["start-and-exit", box.sessionDir, box.cwd, box.agentDir, out]);
	const info = await readJson(out, child);
	pids.push(info.pid, info.grandchild);
	const result = await exited(child);
	expect(result.code, (child as any).output()).toBe(0);
	await waitFor(() => !pidAlive(info.pid) && !pidAlive(info.grandchild), {
		label: "managed process tree gone after pi exit",
		timeoutMs: 8000,
	});
});

it("SIGTERM to the pi process stops managed processes", async () => {
	const box = fresh();
	const out = box.file("out.json");
	const child = spawnChild(["start-and-wait", box.sessionDir, box.cwd, box.agentDir, out]);
	const info = await readJson(out, child);
	pids.push(info.pid, info.grandchild);
	expect(pidAlive(info.pid)).toBe(true);
	expect(pidAlive(info.grandchild)).toBe(true);
	child.kill("SIGTERM");
	const result = await exited(child);
	expect(result.signal === "SIGTERM" || result.code !== null, (child as any).output()).toBe(true);
	await waitFor(() => !pidAlive(info.pid) && !pidAlive(info.grandchild), {
		label: "managed process tree gone after SIGTERM",
		timeoutMs: 8000,
	});
});

it("a later pi process resumes the session and reads finished records", async () => {
	const box = fresh();
	const out1 = box.file("first.json");
	const first = spawnChild(["run-to-exit", box.sessionDir, box.cwd, box.agentDir, out1]);
	const info = await readJson(out1, first);
	expect((await exited(first)).code, (first as any).output()).toBe(0);
	await sleep(100);

	const out2 = box.file("second.json");
	const second = spawnChild(["resume-read", info.sessionFile, box.cwd, box.agentDir, out2, info.id]);
	const view = await readJson(out2, second);
	expect((await exited(second)).code, (second as any).output()).toBe(0);
	const record = view.list.find((p: any) => p.id === info.id);
	expect(record, JSON.stringify(view.list)).toBeTruthy();
	expect(record.state).toBe("exited");
	expect(record.exitCode).toBe(7);
	expect(record.name).toBe("short-job");
	expect(view.logs.lines[0]).toBe("line 1 started");
	expect(view.logs.lines.at(-1)).toBe("line final exiting");
	expect(view.logs.total).toBe(view.logs.lines.length);
});
