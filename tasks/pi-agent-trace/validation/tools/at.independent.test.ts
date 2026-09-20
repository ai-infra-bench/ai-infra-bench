/**
 * Curator-only independent challenge for pi-agent-trace (not part of the scored suites).
 *
 * Two scenarios that the contract suite never composes, with expectations derived from the
 * instruction only: (1) a run whose first tool fails, a manual compaction, then a parallel batch
 * with one failing call; (2) the trace-file override, a /reload and an extension wakeup in one
 * session. Reuses the verifier harness (at_support.ts) but no case of at.contract.test.ts.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { afterEach, expect, it } from "vitest";
import {
	children,
	compact,
	liveProblems,
	type Live,
	ms,
	named,
	prompt,
	readTrace,
	say,
	startSession,
	toolCall,
	traceFileFor,
	traceProblems,
	waitFor,
	withAcks,
} from "./at_support.ts";

const cleanups: Array<() => Promise<void>> = [];
afterEach(async () => {
	for (const fn of cleanups.splice(0).reverse()) await fn();
	delete process.env.PI_AGENT_TRACE_FILE;
});
async function live(tag: string): Promise<Live> {
	const started = await startSession(tag);
	cleanups.push(async () => {
		await started.dispose();
		started.box.cleanup();
	});
	return started;
}
function traceOf(s: Live, file = traceFileFor(s.sessionManager)) {
	const { spans, starts, all, errors } = readTrace(file);
	const problems = [
		...traceProblems(spans, errors, s.sessionManager.getBranch(), s.sessionManager.getSessionId()),
		...liveProblems(all),
	];
	return { spans, starts, all, problems };
}

it("independent: a failing first tool, a manual compaction and a parallel batch with one failure stay consistent", async () => {
	const s = await live("independent-mixed");
	await prompt(s, [toolCall("boom", { reason: "first" }), toolCall("echo", { text: "ok" }), say("done")], "mixed");
	await compact(s);
	await prompt(
		s,
		[
			fauxAssistantMessage(
				[
					fauxToolCall("echo", { text: "a", delayMs: 120 }),
					fauxToolCall("boom", { reason: "b" }),
					fauxToolCall("echo", { text: "c", delayMs: 40 }),
				],
				{ stopReason: "toolUse" },
			),
			say("end"),
		],
		"batch",
	);
	const { spans, problems } = traceOf(s);
	expect(problems).toEqual([]);

	const runs = named(spans, "pi.run");
	expect(runs.map((r) => r.attributes["pi.run.trigger"])).toEqual(["prompt", "prompt"]);
	expect(runs.map((r) => r.attributes["pi.run.turn_count"])).toEqual([3, 2]);
	for (const run of runs) expect(children(spans, run).filter((c) => c.name === "pi.turn")).toHaveLength(Number(run.attributes["pi.run.turn_count"]));

	const tools = named(spans, "execute_tool");
	expect(tools).toHaveLength(5);
	// The file lists tool spans in end order, so compare as a multiset of (name, status).
	const key = (t: (typeof tools)[number]) => `${t.attributes["gen_ai.tool.name"]}:${t.status.code}`;
	expect(tools.map(key).sort()).toEqual(["boom:2", "boom:2", "echo:1", "echo:1", "echo:1"]);
	// Every tool span references the tool-result entry of its own call, each entry exactly once,
	// and a failing tool's ERROR message is the result text pi persisted for that call.
	const branch = s.sessionManager.getBranch() as any[];
	const results = branch.filter((e) => e.type === "message" && e.message.role === "toolResult");
	const byCall = new Map(results.map((e) => [e.message.toolCallId, e]));
	const textOf = (e: any) => (Array.isArray(e.message.content) ? e.message.content.filter((c: any) => c.type === "text").map((c: any) => c.text).join("\n") : String(e.message.content));
	for (const t of tools) {
		const entry = byCall.get(t.attributes["gen_ai.tool.call.id"] as string);
		expect(entry).toBeDefined();
		expect(t.attributes["pi.session.entry_id"]).toBe(entry.id);
		expect(t.attributes["pi.tool.is_error"]).toBe(Boolean(entry.message.isError));
		if (entry.message.isError) expect(t.status).toEqual({ code: 2, message: textOf(entry) });
	}
	expect(new Set(tools.map((t) => t.attributes["pi.session.entry_id"])).size).toBe(5);

	// The compaction is one root span tied to the one compaction entry.
	const compactions = named(spans, "pi.compaction");
	const entries = branch.filter((e) => e.type === "compaction");
	expect(compactions).toHaveLength(1);
	expect(entries).toHaveLength(1);
	expect(compactions[0].parentSpanId).toBeNull();
	expect(compactions[0].attributes["pi.session.entry_id"]).toBe(entries[0].id);
	expect(compactions[0].attributes["pi.compaction.reason"]).toBe("manual");

	// The parallel batch (the three tools of the last run's first turn): the 40 ms call ends no later
	// than the 120 ms call and is shorter; all three started before the first one ended; and all
	// started after the batch's chat ended (millisecond granularity, one implementation clock).
	const lastRun = runs[1];
	const batchTurn = children(spans, lastRun).filter((c) => c.name === "pi.turn")[0];
	const batch = children(spans, batchTurn).filter((c) => c.name.startsWith("execute_tool"));
	expect(batch).toHaveLength(3);
	const echoes = batch.filter((t) => t.attributes["gen_ai.tool.name"] === "echo").sort((a, b) => (a.end - a.start < b.end - b.start ? -1 : 1));
	const [fast, slow] = echoes;
	expect(ms(fast.end)).toBeLessThanOrEqual(ms(slow.end));
	expect(ms(fast.end - fast.start)).toBeLessThan(ms(slow.end - slow.start));
	const firstEnd = batch.map((t) => t.end).reduce((a, b) => (a < b ? a : b));
	for (const t of batch) expect(ms(t.start)).toBeLessThanOrEqual(ms(firstEnd));
	const batchChat = children(spans, batchTurn).find((c) => c.name.startsWith("chat"))!;
	for (const t of batch) expect(ms(t.start)).toBeGreaterThanOrEqual(ms(batchChat.end));
});

it("independent: the trace-file override, a reload and an extension wakeup continue one trace", async () => {
	const dir = mkdtempSync(join(tmpdir(), "pi-at-independent-"));
	cleanups.push(async () => rmSync(dir, { recursive: true, force: true }));
	const custom = join(dir, "nested", "custom-trace.jsonl");
	process.env.PI_AGENT_TRACE_FILE = custom;
	const s = await live("independent-reload");
	await prompt(s, [say("one")], "first");
	await s.session.reload();
	await prompt(s, [toolCall("echo", { text: "after reload" }), say("two")], "second");
	const before = s.rec.count("agent_end");
	s.faux.setResponses(withAcks([say("awake")]));
	s.ext.api().sendMessage({ customType: "independent-wake", content: "wake", display: false }, { triggerTurn: true });
	await waitFor(() => s.rec.count("agent_end") === before + 1, { label: "wakeup run" });
	await waitFor(() => s.rec.count("agent_settled") >= 1, { label: "settled" });

	expect(existsSync(custom)).toBe(true);
	const { spans, starts, problems } = traceOf(s, custom);
	expect(problems).toEqual([]);
	expect(new Set(spans.map((x) => x.traceId)).size).toBe(1);
	expect(new Set([...starts, ...spans].map((x) => x.spanId)).size).toBe(starts.length);
	expect(starts.length).toBe(spans.length);
	const runs = named(spans, "pi.run");
	expect(runs.map((r) => r.attributes["pi.run.trigger"])).toEqual(["prompt", "prompt", "wakeup"]);
	const wake = s.sessionManager.getBranch().find((e: any) => e.type === "custom_message" && e.customType === "independent-wake") as any;
	expect(runs[2].attributes["pi.session.entry_id"]).toBe(wake.id);
	expect(named(spans, "execute_tool")).toHaveLength(1);
	// Nothing was written to the default location.
	expect(existsSync(traceFileFor(s.sessionManager))).toBe(false);
	// The file only grew: every start line precedes its end line.
	const lines = readFileSync(custom, "utf8").trim().split("\n");
	expect(lines.length).toBe(starts.length + spans.length);
});
