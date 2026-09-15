/**
 * Behavioral contract for the background-processes extension.
 *
 * Every case drives a real AgentSession through the public SDK with the faux
 * provider and real fixture processes, and observes only public results: tool
 * results, the session message stream, the session file, and OS process state.
 */
import { existsSync } from "node:fs";
import { afterEach, expect, it } from "vitest";
import {
	BG_TOOLS,
	customEntriesInFile,
	emitCommand,
	firstUserEntryId,
	killGroupQuietly,
	type Live,
	type LiveRuntime,
	payload,
	pidAlive,
	prompt,
	rawText,
	readPid,
	say,
	sleep,
	startRuntime,
	startSession,
	toolCall,
	WAKE_TYPE,
	waitFor,
	withAcks,
} from "./bg_support.ts";

const lives: Array<{ dispose: () => Promise<void>; box: { cleanup: () => void }; drain: () => Promise<void> }> = [];
const pids: number[] = [];

afterEach(async () => {
	for (const live of lives.splice(0)) {
		try {
			await live.drain();
		} catch {
			// a failed test may leave the session unusable; the pid sweep below still runs
		}
		try {
			await live.dispose();
		} catch {
			// disposed already
		}
		live.box.cleanup();
	}
	for (const pid of pids.splice(0)) killGroupQuietly(pid);
});

async function live(tag: string): Promise<Live> {
	const value = await startSession(tag);
	lives.push({ ...value, drain: () => drain(value) });
	return value;
}

async function runtime(tag: string): Promise<LiveRuntime> {
	const value = await startRuntime(tag);
	lives.push({ ...value, drain: () => drainRuntime(value) });
	return value;
}

function messages(session: Live["session"]) {
	return session.messages;
}

function wakeMessages(session: Live["session"]) {
	return messages(session)
		.map((message, index) => ({ message, index }))
		.filter(({ message }) => message.role === "custom" && (message as any).customType === WAKE_TYPE)
		.map(({ message, index }) => ({ index, details: (message as any).details as any }));
}

function toolResultIndex(session: Live["session"], toolName: string, nth = 0): number {
	const hits = messages(session)
		.map((message, index) => ({ message, index }))
		.filter(({ message }) => message.role === "toolResult" && (message as any).toolName === toolName);
	const hit = hits[nth];
	if (!hit) throw new Error(`tool result ${toolName}#${nth} not found`);
	return hit.index;
}

function assistantTextIndex(session: Live["session"], text: string): number {
	const index = messages(session).findIndex(
		(message) =>
			message.role === "assistant" &&
			message.content.some((block) => block.type === "text" && block.text.includes(text)),
	);
	if (index < 0) throw new Error(`assistant text ${JSON.stringify(text)} not found`);
	return index;
}

/** Stop every still-running process through the public tools so its exit wake lands in this session. */
async function drain(l: Live) {
	await prompt(l, [toolCall("bg_list", {}), say("drain list")]);
	const list = payload(l.rec.lastResult("bg_list"));
	const running = (list.processes ?? list).filter((p: any) => p.state === "running");
	if (running.length === 0) return;
	await prompt(l, [...running.map((p: any) => toolCall("bg_kill", { id: p.id, timeoutSec: 1 })), say("drained")]);
	await sleep(200);
}

async function drainRuntime(r: LiveRuntime) {
	const rec = await r.rebind();
	r.faux.setResponses(withAcks([toolCall("bg_list", {}), say("drain list")]));
	await r.runtime.session.prompt("drain", { expandPromptTemplates: false, source: "interactive" });
	const list = payload(rec.lastResult("bg_list"));
	const running = (list.processes ?? list).filter((p: any) => p.state === "running");
	if (running.length === 0) return;
	r.faux.setResponses(
		withAcks([...running.map((p: any) => toolCall("bg_kill", { id: p.id, timeoutSec: 1 })), say("drained")]),
	);
	await r.runtime.session.prompt("drain kill", { expandPromptTemplates: false, source: "interactive" });
	await sleep(200);
}

async function startProcess(l: Live, flags: string, extra: Record<string, unknown> = {}, id?: string) {
	const pidfile = l.box.file(`${id ?? "proc"}-${Math.random().toString(36).slice(2)}.pid`);
	await prompt(l, [
		toolCall("bg_run", { command: emitCommand(`${flags} --pidfile ${pidfile}`), ...extra }, id),
		say("started"),
	]);
	const rec = payload(l.rec.lastResult("bg_run"));
	pids.push(await readPid(pidfile));
	return { rec, pidfile };
}

it("registers bg_run, bg_logs, bg_list, bg_kill and bg_watch", async () => {
	const l = await live("register");
	const names = l.ext
		.api()
		.getAllTools()
		.map((tool) => tool.name);
	for (const tool of BG_TOOLS) expect(names, `missing tool ${tool}`).toContain(tool);
	await prompt(l, [toolCall("bg_list", {}), say("listed")]);
	const list = payload(l.rec.lastResult("bg_list"));
	expect(Array.isArray(list.processes ?? list)).toBe(true);
});

it("bg_run returns a running record and bg_logs pages output in order", async () => {
	const l = await live("run-logs");
	const { rec } = await startProcess(l, "--exit-after 60000", { name: "dev-server" });
	expect(rec.state).toBe("running");
	expect(rec.name).toBe("dev-server");
	expect(typeof rec.id).toBe("string");
	expect(typeof rec.pid).toBe("number");
	expect(pidAlive(rec.pid)).toBe(true);
	expect(rec.exitCode).toBeNull();
	expect(rec.endedAt).toBeNull();

	await sleep(150);
	await prompt(l, [toolCall("bg_logs", { id: rec.id, offset: 0, limit: 2 }), say("paged")]);
	const page = payload(l.rec.lastResult("bg_logs"));
	expect(page.offset).toBe(0);
	expect(page.lines).toEqual(["line 1 started", "line 2 warming up"]);
	expect(page.total).toBeGreaterThanOrEqual(2);

	await prompt(l, [toolCall("bg_logs", { id: rec.id, offset: 1, limit: 1 }), say("paged again")]);
	const second = payload(l.rec.lastResult("bg_logs"));
	expect(second.offset).toBe(1);
	expect(second.lines).toEqual(["line 2 warming up"]);

	await prompt(l, [toolCall("bg_kill", { id: rec.id, timeoutSec: 1 }), say("killed")]);
	const killed = payload(l.rec.lastResult("bg_kill"));
	expect(killed.state).toBe("killed");
	await waitFor(() => !pidAlive(rec.pid), { label: "process gone" });
});

it("bg_logs bounds a page to 64 KB and serves the newest lines by default", async () => {
	const l = await live("logs-bound");
	const { rec } = await startProcess(l, "--flood-mb 2 --exit-after 0");
	await waitFor(() => wakeMessages(l.session).length === 1, { label: "exit wake", timeoutMs: 8000 });
	await prompt(l, [toolCall("bg_logs", { id: rec.id }), say("default page")]);
	const page = payload(l.rec.lastResult("bg_logs"));
	const bytes = Buffer.byteLength(page.lines.join("\n"), "utf8");
	expect(bytes).toBeLessThanOrEqual(64 * 1024);
	expect(page.lines.at(-1)).toBe("line final exiting");
	expect(page.offset + page.lines.length).toBe(page.total);
	expect(page.offset).toBeGreaterThan(0);
});

it("exit wakes an idle agent exactly once with the exit code", async () => {
	const l = await live("exit-wake");
	const { rec } = await startProcess(l, "--exit-after 800 --exit-code 3");
	const turnsBefore = l.rec.count("agent_start");
	const wake = (await waitFor(() => wakeMessages(l.session)[0], { label: "exit wake" })).details;
	expect(wake.id).toBe(rec.id);
	expect(wake.name).toBe(rec.name);
	expect(wake.reasons).toEqual(["exit"]);
	expect(wake.exitCode).toBe(3);
	expect(wake.matchedLine).toBeNull();
	await waitFor(() => l.rec.count("agent_start") > turnsBefore, { label: "wake-triggered turn" });
	await waitFor(() => l.rec.count("agent_settled") >= 2, { label: "agent settled after wake" });
	await sleep(400);
	expect(wakeMessages(l.session)).toHaveLength(1);
	await prompt(l, [toolCall("bg_list", {}), say("listed")]);
	const list = payload(l.rec.lastResult("bg_list"));
	const entry = (list.processes ?? list).find((p: any) => p.id === rec.id);
	expect(entry.state).toBe("exited");
	expect(entry.exitCode).toBe(3);
	expect(typeof entry.endedAt).toBe("string");
});

it("ready wakes once and is delivered after the running tool batch", async () => {
	const l = await live("ready-wake");
	const pidfile = l.box.file("ready.pid");
	await prompt(l, [
		toolCall("bg_run", {
			command: emitCommand(`--ready-after 150 --exit-after 60000 --pidfile ${pidfile}`),
			wake: { ready: "^READY" },
		}),
		toolCall("slow_wait", { ms: 1200 }),
		say("after slow wait"),
	]);
	const rec = payload(l.rec.lastResult("bg_run"));
	pids.push(await readPid(pidfile));
	const wakes = wakeMessages(l.session);
	expect(wakes).toHaveLength(1);
	expect(wakes[0]!.details.reasons).toEqual(["ready"]);
	expect(wakes[0]!.details.matchedLine).toBe("READY server listening on 8080");
	expect(wakes[0]!.details.exitCode).toBeNull();
	const slowIndex = toolResultIndex(l.session, "slow_wait");
	const doneIndex = assistantTextIndex(l.session, "after slow wait");
	expect(wakes[0]!.index).toBeGreaterThan(slowIndex);
	expect(wakes[0]!.index).toBeLessThan(doneIndex);
	await sleep(300);
	expect(wakeMessages(l.session)).toHaveLength(1);
	await prompt(l, [toolCall("bg_kill", { id: rec.id, timeoutSec: 1 }), say("killed")]);
});

it("bg_kill escalates to SIGKILL, removes grandchildren and wakes once", async () => {
	const l = await live("kill");
	const grandchildPidfile = l.box.file("grandchild.pid");
	const { rec } = await startProcess(l, `--ignore-sigterm --spawn-grandchild ${grandchildPidfile} --exit-after 60000`);
	const grandchild = await readPid(grandchildPidfile);
	pids.push(grandchild);
	expect(pidAlive(rec.pid)).toBe(true);
	expect(pidAlive(grandchild)).toBe(true);

	const started = Date.now();
	await prompt(l, [toolCall("bg_kill", { id: rec.id, timeoutSec: 1 }), say("killed")]);
	const killed = payload(l.rec.lastResult("bg_kill"));
	expect(killed.state).toBe("killed");
	expect(Date.now() - started).toBeGreaterThanOrEqual(900);
	await waitFor(() => !pidAlive(rec.pid) && !pidAlive(grandchild), { label: "group gone" });

	await sleep(400);
	const wakes = wakeMessages(l.session);
	expect(wakes).toHaveLength(1);
	expect(wakes[0]!.details.reasons).toEqual(["exit"]);
	await prompt(l, [toolCall("bg_list", {}), say("listed")]);
	const list = payload(l.rec.lastResult("bg_list"));
	expect((list.processes ?? list).find((p: any) => p.id === rec.id).state).toBe("killed");
});

it("bg_watch silences the exit wake and drops patterns", async () => {
	const l = await live("watch");
	const silent = await startProcess(l, "--exit-after 1200");
	await prompt(l, [toolCall("bg_watch", { id: silent.rec.id, exit: false }), say("silenced")]);
	const readyPidfile = l.box.file("watch-ready.pid");
	await prompt(l, [
		toolCall("bg_run", {
			command: emitCommand(`--ready-after 1200 --exit-after 2000 --pidfile ${readyPidfile}`),
			wake: { ready: "^READY" },
		}),
		say("started second"),
	]);
	pids.push(await readPid(readyPidfile));
	const second = payload(l.rec.toolResults("bg_run").at(-1)!);
	await prompt(l, [toolCall("bg_watch", { id: second.id, ready: null }), say("dropped ready")]);
	await sleep(3000);
	const wakes = wakeMessages(l.session);
	expect(wakes.map((w) => w.details.id)).toEqual([second.id]);
	expect(wakes[0]!.details.reasons).toEqual(["exit"]);
});

it("cleanup runs after the group is gone and a failing cleanup is reported", async () => {
	const l = await live("cleanup");
	const marker = l.box.file("cleanup-ran.txt");
	const pidfile = l.box.file("cleanup.pid");
	await prompt(l, [
		toolCall("bg_run", {
			command: emitCommand(`--exit-after 60000 --pidfile ${pidfile}`),
			cleanup: { command: `sh -c 'echo CLEANED > ${JSON.stringify(marker)}; echo CLEANED; exit 3'`, timeoutSec: 5 },
		}),
		say("started"),
	]);
	const rec = payload(l.rec.lastResult("bg_run"));
	const pid = await readPid(pidfile);
	pids.push(pid);
	await prompt(l, [toolCall("bg_kill", { id: rec.id, timeoutSec: 1 }), say("killed")]);
	const killed = payload(l.rec.lastResult("bg_kill"));
	expect(killed.state).toBe("killed");
	expect(killed.cleanup).toBeTruthy();
	expect(killed.cleanup.ran).toBe(true);
	expect(killed.cleanup.failed).toBe(true);
	expect(killed.cleanup.exitCode).toBe(3);
	expect(existsSync(marker)).toBe(true);
	expect(pidAlive(pid)).toBe(false);
	await prompt(l, [toolCall("bg_logs", { id: rec.id }), say("logs")]);
	const page = payload(l.rec.lastResult("bg_logs"));
	expect(page.lines.some((line: string) => line.includes("CLEANED"))).toBe(true);

	await prompt(l, [
		toolCall("bg_run", { command: emitCommand("--exit-after 60000"), cleanup: { command: "true" } }),
		say("s"),
	]);
	const ok = payload(l.rec.lastResult("bg_run"));
	await prompt(l, [toolCall("bg_kill", { id: ok.id, timeoutSec: 1 }), say("k")]);
	const okKilled = payload(l.rec.lastResult("bg_kill"));
	expect(okKilled.cleanup.ran).toBe(true);
	expect(okKilled.cleanup.failed).toBe(false);
});

it("processes survive extension reload", async () => {
	const l = await live("reload");
	const { rec } = await startProcess(l, "--exit-after 60000");
	l.faux.setResponses(withAcks([say("reloaded")]));
	await l.session.prompt("/bg-verifier-reload", { expandPromptTemplates: true, source: "interactive" });
	expect(pidAlive(rec.pid)).toBe(true);
	await prompt(l, [toolCall("bg_list", {}), say("listed")]);
	const list = payload(l.rec.lastResult("bg_list"));
	const entry = (list.processes ?? list).find((p: any) => p.id === rec.id);
	expect(entry.state).toBe("running");
	await prompt(l, [toolCall("bg_kill", { id: rec.id, timeoutSec: 1 }), say("killed")]);
	await waitFor(() => !pidAlive(rec.pid), { label: "process gone after reload kill" });
});

it("processes survive new session and fork and remain killable", async () => {
	const r = await runtime("runtime");
	let rec = await r.rebind();
	const pidfile = r.box.file("runtime.pid");
	r.faux.setResponses(
		withAcks([
			toolCall("bg_run", { command: emitCommand(`--exit-after 60000 --pidfile ${pidfile}`) }),
			say("started"),
		]),
	);
	await r.runtime.session.prompt("start", { expandPromptTemplates: false, source: "interactive" });
	const started = payload(rec.lastResult("bg_run"));
	const pid = await readPid(pidfile);
	pids.push(pid);
	const originalFile = r.runtime.session.sessionFile!;
	const forkEntry = firstUserEntryId(r.runtime.session.sessionManager as any);

	await r.runtime.newSession();
	rec = await r.rebind();
	r.faux.setResponses(withAcks([toolCall("bg_list", {}), say("listed")]));
	await r.runtime.session.prompt("list", { expandPromptTemplates: false, source: "interactive" });
	let list = payload(rec.lastResult("bg_list"));
	expect((list.processes ?? list).find((p: any) => p.id === started.id).state).toBe("running");
	expect(pidAlive(pid)).toBe(true);

	await r.runtime.switchSession(originalFile);
	await r.runtime.fork(forkEntry);
	rec = await r.rebind();
	r.faux.setResponses(
		withAcks([toolCall("bg_list", {}), toolCall("bg_kill", { id: started.id, timeoutSec: 1 }), say("done")]),
	);
	await r.runtime.session.prompt("fork-list", { expandPromptTemplates: false, source: "interactive" });
	list = payload(rec.lastResult("bg_list"));
	expect((list.processes ?? list).find((p: any) => p.id === started.id).state).toBe("running");
	expect(payload(rec.lastResult("bg_kill")).state).toBe("killed");
	await waitFor(() => !pidAlive(pid), { label: "process gone after fork kill" });
});

it("wake goes to the active session after the starting session was replaced", async () => {
	const r = await runtime("handover");
	let rec = await r.rebind();
	const pidfile = r.box.file("handover.pid");
	r.faux.setResponses(
		withAcks([
			toolCall("bg_run", { command: emitCommand(`--exit-after 2000 --exit-code 4 --pidfile ${pidfile}`) }),
			say("started"),
		]),
	);
	await r.runtime.session.prompt("start", { expandPromptTemplates: false, source: "interactive" });
	payload(rec.lastResult("bg_run"));
	pids.push(await readPid(pidfile));
	const originalFile = r.runtime.session.sessionFile!;
	await r.runtime.newSession();
	rec = await r.rebind();
	r.faux.setResponses(withAcks([]));
	const wake = await waitFor(() => wakeMessages(r.runtime.session)[0], {
		label: "wake in replacement session",
		timeoutMs: 8000,
	});
	expect(wake.details.reasons).toEqual(["exit"]);
	expect(wake.details.exitCode).toBe(4);
	await sleep(300);
	expect(customEntriesInFile(originalFile)).toBe(0);
	expect(rec.count("agent_start")).toBeGreaterThanOrEqual(1);
});

it("two processes firing in one window wake in first-fire order", async () => {
	const l = await live("order");
	const a = l.box.file("order-a.pid");
	const b = l.box.file("order-b.pid");
	await prompt(l, [
		toolCall("bg_run", {
			command: emitCommand(`--ready-after 800 --exit-after 60000 --pidfile ${a}`),
			name: "late",
			wake: { ready: "^READY" },
		}),
		toolCall("bg_run", {
			command: emitCommand(`--ready-after 100 --exit-after 60000 --pidfile ${b}`),
			name: "early",
			wake: { ready: "^READY" },
		}),
		toolCall("slow_wait", { ms: 1500 }),
		say("after slow wait"),
	]);
	for (const call of l.rec.toolResults("bg_run")) payload(call);
	pids.push(await readPid(a), await readPid(b));
	const wakes = wakeMessages(l.session);
	expect(wakes.map((w) => w.details.name)).toEqual(["early", "late"]);
	const slowIndex = toolResultIndex(l.session, "slow_wait");
	expect(wakes[0]!.index).toBeGreaterThan(slowIndex);
	expect(wakes[1]!.index).toBeGreaterThan(wakes[0]!.index);
	for (const call of l.rec.toolResults("bg_run")) {
		await prompt(l, [toolCall("bg_kill", { id: payload(call).id, timeoutSec: 1 }), say("k")]);
	}
});

it("bash keeps the built-in contract for commands that finish before the silence threshold", async () => {
	const l = await live("bash-normal");
	// Records belong to the pi process, so earlier cases in this worker may have left some.
	await prompt(l, [toolCall("bg_list", {}), say("baseline")]);
	const before = payload(l.rec.lastResult("bg_list")).processes.length;
	const started = Date.now();
	await prompt(l, [
		toolCall("bash", { command: "printf 'alpha\\nbeta\\n'; printf 'gamma\\n' 1>&2", stalledSec: 5 }, "ok"),
		toolCall("bash", { command: "echo partial; exit 3", stalledSec: 5 }, "fail"),
		toolCall("bash", { command: "echo before; sleep 30", timeout: 1, stalledSec: 5 }, "slow"),
		say("bash done"),
	]);
	const elapsed = Date.now() - started;
	const [ok, fail, slow] = l.rec.toolResults("bash");
	expect(ok, "first bash result").toBeDefined();
	expect(ok!.isError).toBe(false);
	expect(rawText(ok!)).toContain("alpha\nbeta");
	expect(rawText(ok!)).toContain("gamma");
	expect(fail!.isError).toBe(true);
	expect(rawText(fail!)).toContain("partial");
	expect(rawText(fail!)).toMatch(/Command exited with code 3\s*$/);
	expect(slow!.isError).toBe(true);
	expect(rawText(slow!)).toContain("before");
	expect(rawText(slow!)).toMatch(/Command timed out after 1 seconds\s*$/);
	// The timeout (1 s) beat the silence threshold (5 s); nothing lingered.
	expect(elapsed).toBeLessThan(4500);
	// None of the three commands became a background process, and nothing woke the agent.
	await prompt(l, [toolCall("bg_list", {}), say("listed")]);
	expect(payload(l.rec.lastResult("bg_list")).processes).toHaveLength(before);
	expect(wakeMessages(l.session)).toHaveLength(0);
});

it("a silent bash command moves to the background and its next output and exit wake the agent", async () => {
	const l = await live("bash-stall");
	const pidfile = l.box.file("stall.pid");
	const started = Date.now();
	await prompt(l, [
		toolCall("bash", {
			command: emitCommand(`--ready-after 2400 --exit-after 3800 --exit-code 4 --pidfile ${pidfile}`),
			stalledSec: 1,
		}),
		say("moved on"),
	]);
	const elapsed = Date.now() - started;
	const call = l.rec.lastResult("bash");
	// Returned after the 1 s silence threshold and well before the command spoke again at 2.4 s.
	expect(elapsed).toBeGreaterThanOrEqual(1000);
	expect(elapsed).toBeLessThan(2200);
	expect(call.isError).toBe(false);
	const rec = payload(call);
	expect(rec.backgrounded).toBe(true);
	expect(rec.stalledSec).toBe(1);
	expect(rec.state).toBe("running");
	expect(typeof rec.id).toBe("string");
	pids.push(await readPid(pidfile));
	expect(pidAlive(rec.pid)).toBe(true);

	await prompt(l, [toolCall("bg_logs", { id: rec.id, offset: 0 }), toolCall("bg_list", {}), say("checked")]);
	expect(payload(l.rec.lastResult("bg_logs")).lines.slice(0, 2)).toEqual(["line 1 started", "line 2 warming up"]);
	const listed = payload(l.rec.lastResult("bg_list")).processes.find((p: any) => p.id === rec.id);
	expect(listed.state).toBe("running");
	expect(listed.backgrounded).toBe(true);

	const first = (await waitFor(() => wakeMessages(l.session)[0], { label: "output wake", timeoutMs: 6000 })).details;
	expect(first.id).toBe(rec.id);
	expect(first.reasons).toEqual(["output"]);
	expect(first.matchedLine).toBe("READY server listening on 8080");
	expect(first.exitCode).toBeNull();
	const second = (await waitFor(() => wakeMessages(l.session)[1], { label: "exit wake", timeoutMs: 6000 })).details;
	expect(second.id).toBe(rec.id);
	expect(second.reasons).toEqual(["exit"]);
	expect(second.exitCode).toBe(4);
	await waitFor(() => !l.session.isStreaming, { label: "settled after exit wake", timeoutMs: 6000 });
	await sleep(400);
	// "line final exiting" was a second output line; output wakes once per process.
	expect(wakeMessages(l.session)).toHaveLength(2);
	await prompt(l, [toolCall("bg_list", {}), say("final")]);
	const final = payload(l.rec.lastResult("bg_list")).processes.find((p: any) => p.id === rec.id);
	expect(final.state).toBe("exited");
	expect(final.exitCode).toBe(4);
	expect(final.backgrounded).toBe(true);
});

it("log flood is paged from disk without growing the heap", { timeout: 60_000 }, async () => {
	expect(typeof global.gc, "test.sh must run vitest with --expose-gc").toBe("function");
	const l = await live("flood");
	global.gc!();
	const before = process.memoryUsage().heapUsed;
	const { rec } = await startProcess(l, "--flood-mb 48 --exit-after 0");
	await waitFor(() => wakeMessages(l.session).length === 1, { label: "flood exit wake", timeoutMs: 20000 });
	global.gc!();
	const after = process.memoryUsage().heapUsed;
	expect(after - before).toBeLessThan(24 * 1024 * 1024);
	await prompt(l, [toolCall("bg_logs", { id: rec.id, offset: 100000, limit: 3 }), say("mid page")]);
	const page = payload(l.rec.lastResult("bg_logs"));
	expect(page.offset).toBe(100000);
	expect(page.lines).toHaveLength(3);
	expect(page.lines[0]).toMatch(/^line 100001 x+$/);
	expect(page.total).toBeGreaterThan(400000);
});
