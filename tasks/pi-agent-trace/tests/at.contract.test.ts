/**
 * Agent-trace contract suite (verifier-owned).
 *
 * Every case drives a real AgentSession with pi's faux provider, then reads the
 * trace file the extension wrote and checks it against the session branch. It
 * never imports candidate code.
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fauxAssistantMessage, fauxText, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { afterEach, describe, expect, it } from "vitest";
import {
	children,
	compact,
	customTexts,
	type Live,
	liveProblems,
	ms,
	named,
	prompt,
	rawText,
	readTrace,
	say,
	sleep,
	type Span,
	startRuntime,
	startSession,
	toolCall,
	TRACE_ID,
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

async function live(tag: string, options: { contextWindow?: number; tokensPerSecond?: number } = {}): Promise<Live> {
	const started = await startSession(tag, options);
	cleanups.push(async () => {
		await started.dispose();
		started.box.cleanup();
	});
	return started;
}

function trace(s: Live) {
	const file = traceFileFor(s.sessionManager);
	const { spans, starts, all, errors } = readTrace(file);
	const problems = [
		...traceProblems(spans, errors, s.sessionManager.getBranch(), s.sessionManager.getSessionId()),
		...liveProblems(all),
	];
	return { file, spans, starts, all, problems };
}

function entryOf(s: Live, pred: (entry: any) => boolean) {
	const hits = s.sessionManager.getBranch().filter(pred);
	return hits;
}

const ns = (millis: number) => BigInt(millis) * 1_000_000n;

describe("agent-trace contract", () => {
	it("a prompt with a tool call exports run, turn, chat and tool spans in OTLP/JSON tied to session entries", async () => {
		const s = await live("basic");
		const file = traceFileFor(s.sessionManager);
		expect(existsSync(file)).toBe(false);
		const before = Date.now();
		await prompt(s, [toolCall("echo", { text: "TOOL-OUTPUT", delayMs: 30 }), say("done")], "run the tool");
		const after = Date.now();
		const { spans, starts, all, problems } = trace(s);
		expect(problems).toEqual([]);
		expect(spans.map((span) => span.name)).toEqual([
			`chat ${s.faux.getModel().id}`,
			"execute_tool echo",
			"pi.turn",
			`chat ${s.faux.getModel().id}`,
			"pi.turn",
			"pi.run",
		]);
		// Start lines appear in start order, each before its children; end lines in end order.
		expect(starts.map((span) => span.name)).toEqual([
			"pi.run",
			"pi.turn",
			`chat ${s.faux.getModel().id}`,
			"execute_tool echo",
			"pi.turn",
			`chat ${s.faux.getModel().id}`,
		]);
		// End lines in end order; the start/end interleaving at one event is the implementation's.
		expect(spans.map((span) => span.name.split(" ")[0])).toEqual([
			"chat",
			"execute_tool",
			"pi.turn",
			"chat",
			"pi.turn",
			"pi.run",
		]);
		expect(starts[0].attributes).toMatchObject({ "pi.span.phase": "start", "pi.run.trigger": "prompt" });
		expect(starts[3].attributes).toMatchObject({
			"gen_ai.tool.name": "echo",
			"gen_ai.operation.name": "execute_tool",
		});
		const [run] = named(spans, "pi.run");
		expect(run.parentSpanId).toBeNull();
		expect(run.kind).toBe(1);
		expect(run.traceId).toMatch(TRACE_ID);
		expect(run.attributes["pi.run.trigger"]).toBe("prompt");
		expect(run.attributes["pi.run.turn_count"]).toBe(2);
		expect(run.attributes["pi.run.steer_count"]).toBe(0);
		expect(run.attributes["pi.run.steer_entry_ids"]).toEqual([]);
		const [userEntry] = entryOf(s, (e) => e.type === "message" && e.message.role === "user");
		expect(run.attributes["pi.session.entry_id"]).toBe(userEntry.id);
		// Verifier-clock windows get 1 ms of slack below: an implementation may anchor a monotonic clock on a
		// millisecond-truncated Date.now() and read up to 1 ms behind the verifier (sub-millisecond digits are its own).
		expect(run.start).toBeGreaterThanOrEqual(ns(before - 1));
		// Sub-millisecond clocks are fine: the run may end inside the millisecond `after` was read in.
		expect(run.end).toBeLessThanOrEqual(ns(after + 1));
		expect(run.status).toEqual({ code: 1 });
		expect(run.resource["service.version"]).toBe("0.85.1");
		expect(run.resource["process.pid"]).toBe(process.pid);

		const turns = children(spans, run);
		expect(turns.map((t) => t.attributes["pi.turn.index"])).toEqual([0, 1]);
		expect(turns.map((t) => t.attributes["pi.turn.stop_reason"])).toEqual(["toolUse", "stop"]);
		expect(turns.map((t) => t.attributes["pi.turn.tool_call_count"])).toEqual([1, 0]);
		// The turn starts at the turn_start event's timestamp; sub-millisecond digits are the implementation's.
		expect(turns.map((t) => t.start / 1_000_000n)).toEqual(
			s.ext.state.turnStarts.map((timestamp) => BigInt(timestamp)),
		);

		const chats = named(spans, "chat");
		expect(chats).toHaveLength(2);
		const assistants = entryOf(s, (e) => e.type === "message" && e.message.role === "assistant");
		for (const [i, chat] of chats.entries()) {
			expect(chat.kind).toBe(3);
			expect(chat.parentSpanId).toBe(turns[i].spanId);
			const usage = assistants[i].message.usage;
			expect(usage.input).toBeGreaterThan(0);
			expect(chat.attributes).toMatchObject({
				"gen_ai.operation.name": "chat",
				"gen_ai.system": s.faux.getModel().provider,
				"gen_ai.request.model": s.faux.getModel().id,
				"gen_ai.usage.input_tokens": usage.input,
				"gen_ai.usage.output_tokens": usage.output,
				"pi.usage.cache_read_tokens": usage.cacheRead,
				"pi.usage.cache_write_tokens": usage.cacheWrite,
				"pi.session.entry_id": assistants[i].id,
			});
			expect(chat.attributes["gen_ai.response.finish_reasons"]).toEqual([i === 0 ? "toolUse" : "stop"]);
		}
		const [tool] = named(spans, "execute_tool");
		const [toolEntry] = entryOf(s, (e) => e.type === "message" && e.message.role === "toolResult");
		expect(tool.parentSpanId).toBe(turns[0].spanId);
		// The attribute table lists what a span carries, not an exhaustive set: listed keys with the right values, extra keys allowed.
		expect(tool.attributes).toMatchObject({
			"gen_ai.operation.name": "execute_tool",
			"gen_ai.tool.name": "echo",
			"gen_ai.tool.call.id": toolEntry.message.toolCallId,
			"pi.tool.is_error": false,
			"pi.session.entry_id": toolEntry.id,
		});
		expect(tool.end - tool.start).toBeGreaterThanOrEqual(ns(25));
		expect(tool.start).toBeGreaterThanOrEqual(chats[0].end);

		// A second prompt appends; nothing earlier is rewritten.
		await prompt(s, [say("again")], "second");
		const again = trace(s);
		expect(again.problems).toEqual([]);
		expect(again.spans.slice(0, 6).map((x) => x.spanId)).toEqual(spans.map((x) => x.spanId));
		expect(again.spans).toHaveLength(9);
		expect(again.all.slice(0, 12).map((x) => x.line)).toEqual(all.map((x) => x.line));
	});

	it("a failing tool and an error response mark tool, chat and turn spans ERROR while the run stays OK", async () => {
		const s = await live("errors");
		await prompt(s, [toolCall("boom", { reason: "kaboom" }), say("recovered")], "fail a tool");
		let { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const [tool] = named(spans, "execute_tool");
		expect(tool.attributes["pi.tool.is_error"]).toBe(true);
		expect(tool.status.code).toBe(2);
		expect(tool.status.message).toBe(rawText(s.rec.lastResult("boom")));
		expect(tool.status.message).toContain("kaboom");
		const [run] = named(spans, "pi.run");
		expect(run.status).toEqual({ code: 1 });
		for (const turn of children(spans, run)) expect(turn.status).toEqual({ code: 1 });

		await prompt(
			s,
			[fauxAssistantMessage(fauxText(""), { stopReason: "error", errorMessage: "upstream 529" })],
			"error turn",
		);
		({ spans, problems } = trace(s));
		expect(problems).toEqual([]);
		const runs = named(spans, "pi.run");
		expect(runs).toHaveLength(2);
		expect(runs[1].status).toEqual({ code: 1 });
		const [turn] = children(spans, runs[1]);
		expect(turn.status).toEqual({ code: 2, message: "upstream 529" });
		expect(turn.attributes["pi.turn.stop_reason"]).toBe("error");
		const [chat] = children(spans, turn);
		expect(chat.status).toEqual({ code: 2, message: "upstream 529" });
		expect(chat.attributes["gen_ai.response.finish_reasons"]).toEqual(["error"]);
	});

	it("runs started by an extension message are wakeups and runs queued at agent_end are continuations", async () => {
		const s = await live("triggers");
		await prompt(s, [say("first")], "prompt one");
		// A context-only message never starts a run and is referenced by no span.
		s.ext
			.api()
			.sendMessage(
				{ customType: "at-verifier-note", content: "for context", display: false },
				{ triggerTurn: false },
			);
		await sleep(20);
		// Wakeup: an extension message that starts a run while pi is idle.
		s.faux.setResponses(withAcks([say("awake")]));
		const runsBefore = s.rec.count("agent_end");
		s.ext
			.api()
			.sendMessage({ customType: "at-verifier-wake", content: "wake up", display: false }, { triggerTurn: true });
		await waitFor(() => s.rec.count("agent_end") === runsBefore + 1, { label: "wakeup run" });
		await waitFor(() => s.rec.count("agent_settled") === runsBefore + 1, { label: "wakeup settled" });
		// Continuation: the verifier extension queues a follow-up at agent_end of the next prompt.
		s.ext.state.queueFollowUp = true;
		await prompt(s, [say("second"), say("continued")], "prompt two");
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const runs = named(spans, "pi.run");
		expect(runs.map((r) => r.attributes["pi.run.trigger"])).toEqual(["prompt", "wakeup", "prompt", "continuation"]);
		const customs = entryOf(s, (e) => e.type === "custom_message");
		expect(customs.map((c) => c.customType)).toEqual([
			"at-verifier-note",
			"at-verifier-wake",
			"at-verifier-followup",
		]);
		expect(runs[1].attributes["pi.session.entry_id"]).toBe(customs[1].id);
		expect(runs[3].attributes["pi.session.entry_id"]).toBe(customs[2].id);
		const users = entryOf(s, (e) => e.type === "message" && e.message.role === "user");
		expect([runs[0], runs[2]].map((r) => r.attributes["pi.session.entry_id"])).toEqual(users.map((u) => u.id));
		expect(runs[3].start).toBeGreaterThanOrEqual(runs[2].end);
		for (const r of runs) expect(r.attributes["pi.run.turn_count"]).toBe(1);
	});

	it("manual and threshold compactions export root compaction spans tied to compaction entries", async () => {
		const s = await live("compaction", { contextWindow: 30_000 });
		await prompt(s, [say("the secret word is alpaca")], "remember");
		await compact(s);
		let { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		let compactions = named(spans, "pi.compaction");
		expect(compactions).toHaveLength(1);
		let [entry] = entryOf(s, (e) => e.type === "compaction");
		expect(compactions[0].parentSpanId).toBeNull();
		expect(entry.usage).toBeDefined();
		expect(compactions[0].attributes).toMatchObject({
			"pi.compaction.reason": "manual",
			"pi.compaction.will_retry": false,
			"pi.compaction.tokens_before": entry.tokensBefore,
			"pi.compaction.first_kept_entry_id": entry.firstKeptEntryId,
			"gen_ai.usage.input_tokens": entry.usage.input,
			"gen_ai.usage.output_tokens": entry.usage.output,
			"pi.session.entry_id": entry.id,
		});
		expect(compactions[0].status).toEqual({ code: 1 });
		expect(spans[spans.length - 1].name).toBe("pi.compaction");

		// Threshold compaction: one large prompt pushes the estimate past contextWindow - reserveTokens.
		// pi ignores usage from an assistant message stamped in the same millisecond as the last
		// compaction, so let a short turn and a few milliseconds pass first.
		await sleep(5);
		await prompt(s, [say("between")], "between");
		await sleep(5);
		const filler = "lorem ipsum ".repeat(3_000);
		await prompt(s, [say("noted")], filler);
		({ spans, problems } = trace(s));
		expect(problems).toEqual([]);
		compactions = named(spans, "pi.compaction");
		expect(compactions).toHaveLength(2);
		const entries = entryOf(s, (e) => e.type === "compaction");
		expect(entries).toHaveLength(2);
		expect(compactions[1].attributes["pi.compaction.reason"]).toBe("threshold");
		expect(compactions[1].attributes["pi.session.entry_id"]).toBe(entries[1].id);
		expect(compactions[1].attributes["pi.compaction.tokens_before"]).toBe(entries[1].tokensBefore);
		expect(compactions[1].attributes["pi.compaction.first_kept_entry_id"]).toBe(entries[1].firstKeptEntryId);
		expect(compactions[1].attributes["gen_ai.usage.input_tokens"]).toBe(entries[1].usage.input);
		expect(compactions[1].attributes["gen_ai.usage.output_tokens"]).toBe(entries[1].usage.output);
		const runs = named(spans, "pi.run");
		expect(compactions[1].start).toBeGreaterThanOrEqual(runs[runs.length - 1].end);
		// The summary requests of a compaction are not chat spans: only assistant entries on the branch are.
		expect(named(spans, "chat")).toHaveLength(
			entryOf(s, (e) => e.type === "message" && e.message.role === "assistant").length,
		);
	});

	it("reload appends to the same file with the same trace id and no duplicate spans", async () => {
		const s = await live("reload");
		await prompt(s, [toolCall("echo", { text: "x" }), say("one")], "first");
		const first = trace(s);
		expect(first.problems).toEqual([]);
		await s.session.reload();
		const afterReload = trace(s);
		expect(afterReload.all.map((x) => [x.phase, x.spanId])).toEqual(first.all.map((x) => [x.phase, x.spanId]));
		await prompt(s, [say("two")], "second");
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		expect(spans).toHaveLength(first.spans.length + 3);
		expect(new Set(spans.map((x) => x.traceId)).size).toBe(1);
		expect(spans.slice(0, first.spans.length).map((x) => x.spanId)).toEqual(first.spans.map((x) => x.spanId));
	});

	it("PI_AGENT_TRACE_FILE replaces the trace file path", async () => {
		const dir = mkdtempSync(join(tmpdir(), "pi-at-override-"));
		cleanups.push(async () => rmSync(dir, { recursive: true, force: true }));
		const override = join(dir, "nested", "trace.jsonl");
		process.env.PI_AGENT_TRACE_FILE = override;
		const s = await live("override");
		await prompt(s, [say("hi")], "hello");
		expect(existsSync(traceFileFor(s.sessionManager))).toBe(false);
		const { spans, all, errors } = readTrace(override);
		const problems = [
			...traceProblems(spans, errors, s.sessionManager.getBranch(), s.sessionManager.getSessionId()),
			...liveProblems(all),
		];
		expect(problems).toEqual([]);
		expect(spans.map((x) => x.name)).toEqual([`chat ${s.faux.getModel().id}`, "pi.turn", "pi.run"]);
	});
	it("an aborted stream marks its chat and turn ERROR and the trace stays consistent afterwards", async () => {
		const s = await live("abort", { tokensPerSecond: 50 });
		s.faux.setResponses(withAcks([fauxAssistantMessage(fauxText("word ".repeat(200)))]));
		const running = s.session.prompt("go", { expandPromptTemplates: false, source: "interactive" });
		await sleep(300);
		await s.session.abort();
		await running;
		let { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const [assistant] = entryOf(s, (e) => e.type === "message" && e.message.role === "assistant");
		expect(assistant.message.stopReason).toBe("aborted");
		const [run] = named(spans, "pi.run");
		expect(run.status).toEqual({ code: 1 });
		const [turn] = children(spans, run);
		expect(turn.status).toEqual({ code: 2, message: assistant.message.errorMessage ?? "aborted" });
		expect(turn.attributes["pi.turn.stop_reason"]).toBe("aborted");
		const [chat] = children(spans, turn);
		expect(chat.status).toEqual({ code: 2, message: assistant.message.errorMessage ?? "aborted" });
		expect(chat.attributes["gen_ai.response.finish_reasons"]).toEqual(["aborted"]);
		expect(chat.attributes["pi.session.entry_id"]).toBe(assistant.id);

		// The next prompt is traced as usual: the abort left no dangling state.
		await prompt(s, [toolCall("echo", { text: "after" }), say("fine")], "again");
		({ spans, problems } = trace(s));
		expect(problems).toEqual([]);
		expect(named(spans, "pi.run")).toHaveLength(2);
		expect(named(spans, "pi.run")[1].status).toEqual({ code: 1 });
		expect(named(spans, "execute_tool")).toHaveLength(1);
	});

	it("a failed compaction exports an ERROR compaction span without an entry id", async () => {
		const s = await live("compact-fail");
		await prompt(s, [say("the secret word is alpaca")], "remember");
		s.faux.setResponses([
			fauxAssistantMessage(fauxText(""), { stopReason: "error", errorMessage: "summary boom" }),
			fauxAssistantMessage(fauxText(""), { stopReason: "error", errorMessage: "summary boom" }),
		]);
		await expect(s.session.compact()).rejects.toThrow();
		expect(s.ext.state.compactFailures).toHaveLength(1);
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const compactions = named(spans, "pi.compaction");
		expect(compactions).toHaveLength(1);
		expect(compactions[0].parentSpanId).toBeNull();
		expect(compactions[0].status).toEqual({ code: 2, message: s.ext.state.compactFailures[0] });
		expect(compactions[0].attributes).toMatchObject({
			"pi.compaction.reason": "manual",
			"pi.compaction.will_retry": false,
		});
		// Nothing from a compaction entry: the compaction failed and pi persisted none.
		for (const key of [
			"pi.compaction.tokens_before",
			"pi.compaction.first_kept_entry_id",
			"gen_ai.usage.input_tokens",
			"gen_ai.usage.output_tokens",
			"pi.session.entry_id",
		]) {
			expect(compactions[0].attributes[key]).toBeUndefined();
		}
		expect(entryOf(s, (e) => e.type === "compaction")).toEqual([]);
		expect(spans[spans.length - 1].name).toBe("pi.compaction");

		// A later, successful compaction is traced normally.
		await compact(s);
		const again = trace(s);
		expect(again.problems).toEqual([]);
		expect(named(again.spans, "pi.compaction").map((c) => c.status.code)).toEqual([2, 1]);
	});

	it("a quit while a run is streaming closes the open spans with status shutdown", async () => {
		const r = await startRuntime("quit", undefined, 50);
		cleanups.push(async () => r.box.cleanup());
		await r.rebind();
		const manager = r.runtime.session.sessionManager;
		r.faux.setResponses(withAcks([fauxAssistantMessage(fauxText("word ".repeat(200)))]));
		const running = r.runtime.session.prompt("go", { expandPromptTemplates: false, source: "interactive" });
		await sleep(300);
		// pi's quit path emits session_shutdown without aborting the run first. The verifier brackets the
		// shutdown with its own clock: every close must fall inside that window, whatever clock reads the
		// implementation takes and however many sub-millisecond digits it adds.
		const shutdownBegan = Date.now();
		await r.runtime.dispose();
		const shutdownEnded = Date.now();
		await running.catch(() => undefined);
		const file = traceFileFor(manager);
		const { spans, starts, all, errors } = readTrace(file);
		const problems = [
			...traceProblems(spans, errors, manager.getBranch(), manager.getSessionId()),
			...liveProblems(all),
		];
		expect(problems).toEqual([]);
		expect(starts.map((x) => x.name)).toEqual(["pi.run", "pi.turn", `chat ${r.faux.getModel().id}`]);
		expect(spans.map((x) => x.name)).toEqual([`chat ${r.faux.getModel().id}`, "pi.turn", "pi.run"]);
		for (const span of spans) expect(span.status).toEqual({ code: 2, message: "shutdown" });
		const [chat, turn, run] = spans;
		expect(chat.parentSpanId).toBe(turn.spanId);
		expect(turn.parentSpanId).toBe(run.spanId);
		expect(run.parentSpanId).toBeNull();
		// The assistant message was never persisted, so the chat span has no entry id; the run's user entry exists.
		expect("pi.session.entry_id" in chat.attributes).toBe(false);
		const [user] = manager.getBranch().filter((e: any) => e.type === "message" && e.message.role === "user");
		expect(run.attributes["pi.session.entry_id"]).toBe(user.id);
		expect(run.attributes["pi.run.turn_count"]).toBe(1);
		for (const span of [chat, turn, run]) {
			expect(span.end).toBeGreaterThanOrEqual(ns(shutdownBegan - 1)); // 1 ms slack, see the first case
			expect(span.end).toBeLessThanOrEqual(ns(shutdownEnded + 1));
		}
		// Written and closed child-first.
		expect(chat.end).toBeLessThanOrEqual(turn.end);
		expect(turn.end).toBeLessThanOrEqual(run.end);
	});

	it("an unwritable trace path never reaches the agent and is reported once", async () => {
		const dir = mkdtempSync(join(tmpdir(), "pi-at-unwritable-"));
		cleanups.push(async () => rmSync(dir, { recursive: true, force: true }));
		const blocker = join(dir, "blocker");
		writeFileSync(blocker, "not a directory");
		const override = join(blocker, "trace.jsonl");
		process.env.PI_AGENT_TRACE_FILE = override;
		const s = await live("unwritable");
		const errors: unknown[] = [];
		s.session.bindExtensions({ onError: (error: unknown) => errors.push(error) } as any);
		await prompt(s, [toolCall("echo", { text: "still works" }), say("done")], "first");
		await prompt(s, [say("second")], "second");
		expect(s.rec.lastResult("echo").isError).toBe(false);
		expect(rawText(s.rec.lastResult("echo"))).toBe("still works");
		expect(s.rec.count("agent_end")).toBe(2);
		expect(existsSync(override)).toBe(false);
		expect(existsSync(traceFileFor(s.sessionManager))).toBe(false);
		const reports = customTexts(s.sessionManager, "agent-trace");
		expect(reports).toHaveLength(1);
		expect(reports[0].startsWith(`agent-trace: cannot write ${override}`)).toBe(true);
		expect(errors, JSON.stringify(errors).slice(0, 300)).toEqual([]);
		expect(s.requests[0].systemPrompt).not.toContain("agent-trace");
		expect(s.requests[s.requests.length - 1].systemPrompt).toBe(s.requests[0].systemPrompt);
		// The report never started a turn of its own.
		expect(s.rec.count("turn_start")).toBe(3);
	});
	it("the file updates live: start lines appear while a tool is still running and end lines complete them", async () => {
		const s = await live("live");
		s.faux.setResponses(withAcks([toolCall("echo", { text: "slow", delayMs: 1_500 }), say("done")]));
		const running = s.session.prompt("go", { expandPromptTemplates: false, source: "interactive" });
		await waitFor(() => s.rec.count("tool_execution_start") === 1, { label: "tool started" });
		await sleep(300);
		// Mid-execution: the run, the turn and the tool have started; the chat has already ended.
		const mid = readTrace(traceFileFor(s.sessionManager));
		expect(mid.errors).toEqual([]);
		expect(liveProblems(mid.all)).toEqual([]);
		// Mid-execution: the run, the turn and the tool have started and the chat has ended, in any interleaving.
		expect(mid.all.map((x) => `${x.phase}:${x.name.split(" ")[0]}`).sort()).toEqual(
			["start:pi.run", "start:pi.turn", "start:chat", "start:execute_tool", "end:chat"].sort(),
		);
		const [runStart, turnStart, , toolStart] = mid.starts;
		expect(turnStart.parentSpanId).toBe(runStart.spanId);
		expect(toolStart.parentSpanId).toBe(turnStart.spanId);
		expect(toolStart.attributes).toMatchObject({
			"pi.span.phase": "start",
			"gen_ai.operation.name": "execute_tool",
			"gen_ai.tool.name": "echo",
		});
		expect(typeof toolStart.attributes["gen_ai.tool.call.id"]).toBe("string");
		const [assistant] = entryOf(s, (e) => e.type === "message" && e.message.role === "assistant");
		expect(mid.spans[0].attributes["pi.session.entry_id"]).toBe(assistant.id);
		expect(mid.spans[0].spanId).toBe(mid.starts[2].spanId);

		await running;
		const done = trace(s);
		expect(done.problems).toEqual([]);
		expect(done.all.slice(0, 5).map((x) => x.line)).toEqual(mid.all.map((x) => x.line));
		expect(
			done.all
				.slice(5)
				.map((x) => `${x.phase}:${x.name.split(" ")[0]}`)
				.sort(),
		).toEqual(
			[
				"end:execute_tool",
				"end:pi.turn",
				"start:pi.turn",
				"start:chat",
				"end:chat",
				"end:pi.turn",
				"end:pi.run",
			].sort(),
		);
		expect(done.spans.map((x) => x.name.split(" ")[0])).toEqual([
			"chat",
			"execute_tool",
			"pi.turn",
			"chat",
			"pi.turn",
			"pi.run",
		]);
		const toolEnd = done.spans.find((x) => x.spanId === toolStart.spanId)!;
		expect(toolEnd.end - toolEnd.start).toBeGreaterThanOrEqual(1_400_000_000n);
		expect(toolEnd.attributes["pi.tool.is_error"]).toBe(false);
	});
	it("concurrent tool calls of one assistant message get one overlapping span each with its own status and entry", async () => {
		const s = await live("parallel");
		await prompt(
			s,
			[
				fauxAssistantMessage(
					[
						fauxToolCall("echo", { text: "slow", delayMs: 300 }),
						fauxToolCall("echo", { text: "fast", delayMs: 100 }),
					],
					{ stopReason: "toolUse" },
				),
				say("done"),
			],
			"two tools",
		);
		let { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		let tools = named(spans, "execute_tool");
		expect(tools).toHaveLength(2);
		// Written in end order: the 100 ms call first; both started before the first ended.
		expect(tools[0].end - tools[0].start).toBeLessThan(tools[1].end - tools[1].start);
		expect(tools[1].start).toBeLessThan(tools[0].end);
		expect(tools[0].parentSpanId).toBe(tools[1].parentSpanId);
		const results = entryOf(s, (e) => e.type === "message" && e.message.role === "toolResult");
		expect(results).toHaveLength(2);
		for (const tool of tools) {
			const result = results.find((r) => r.message.toolCallId === tool.attributes["gen_ai.tool.call.id"]);
			expect(result).toBeDefined();
			expect(tool.attributes["pi.session.entry_id"]).toBe(result.id);
			expect(tool.status).toEqual({ code: 1 });
		}
		const [run] = named(spans, "pi.run");
		expect(children(spans, run)[0].attributes["pi.turn.tool_call_count"]).toBe(2);

		// One failing call beside a succeeding one keeps statuses per span.
		await prompt(
			s,
			[
				fauxAssistantMessage(
					[fauxToolCall("boom", { reason: "half" }), fauxToolCall("echo", { text: "ok", delayMs: 50 })],
					{
						stopReason: "toolUse",
					},
				),
				say("recovered"),
			],
			"mixed",
		);
		({ spans, problems } = trace(s));
		expect(problems).toEqual([]);
		tools = named(spans, "execute_tool").slice(2);
		expect(tools.map((t) => [t.name, t.status.code])).toEqual([
			["execute_tool boom", 2],
			["execute_tool echo", 1],
		]);
		expect(tools[0].status.message).toContain("half");
		const runs = named(spans, "pi.run");
		expect(children(spans, runs[1])[0].attributes["pi.turn.tool_call_count"]).toBe(2);
		expect(runs[1].status).toEqual({ code: 1 });
	});

	it("steering and follow-up messages start turns inside the run and are listed on it, never as new runs", async () => {
		const s = await live("steer", { tokensPerSecond: 40 });
		s.faux.setResponses(
			withAcks([fauxAssistantMessage(fauxText("word ".repeat(120))), say("after steer"), say("after follow-up")]),
		);
		const running = s.session.prompt("go", { expandPromptTemplates: false, source: "interactive" });
		await sleep(300);
		// A context-only message during the run: flushed by pi, referenced by nothing.
		s.ext
			.api()
			.sendMessage(
				{ customType: "at-verifier-note", content: "context only", display: false },
				{ triggerTurn: false },
			);
		await s.session.prompt("steer me", {
			expandPromptTemplates: false,
			source: "interactive",
			streamingBehavior: "steer",
		});
		s.ext
			.api()
			.sendMessage(
				{ customType: "at-verifier-follow", content: "and then", display: false },
				{ deliverAs: "followUp" },
			);
		await running;
		await waitFor(() => s.rec.count("agent_settled") >= 1, { label: "settled" });
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const runs = named(spans, "pi.run");
		expect(runs).toHaveLength(1);
		const [run] = runs;
		expect(run.attributes["pi.run.trigger"]).toBe("prompt");
		expect(run.attributes["pi.run.turn_count"]).toBe(3);
		const users = entryOf(s, (e) => e.type === "message" && e.message.role === "user");
		const customs = entryOf(s, (e) => e.type === "custom_message");
		expect(users).toHaveLength(2);
		expect(customs.map((c) => c.customType)).toEqual(["at-verifier-note", "at-verifier-follow"]);
		expect(run.attributes["pi.session.entry_id"]).toBe(users[0].id);
		expect(run.attributes["pi.run.steer_count"]).toBe(2);
		expect(run.attributes["pi.run.steer_entry_ids"]).toEqual([users[1].id, customs[1].id]);
		const turns = children(spans, run);
		expect(turns.map((t) => t.attributes["pi.turn.index"])).toEqual([0, 1, 2]);
		// A turn starts at pi's millisecond event timestamp while the previous turn ended on the implementation's
		// sub-millisecond clock, so this holds at millisecond granularity only (traceProblems checks the same).
		for (let i = 1; i < turns.length; i++) expect(ms(turns[i].start)).toBeGreaterThanOrEqual(ms(turns[i - 1].end));
		expect(named(spans, "chat")).toHaveLength(3);
	});
	it("overflow recovery persists the failed chat, compacts with will_retry and continues in a run without a message", async () => {
		const s = await live("overflow");
		await prompt(s, [say("the secret word is alpaca")], "remember");
		// An unrelated context-only message: a retry run must not claim it.
		s.ext
			.api()
			.sendMessage(
				{ customType: "at-verifier-note", content: "context only", display: false },
				{ triggerTurn: false },
			);
		await sleep(20);
		s.faux.setResponses([
			fauxAssistantMessage(fauxText(""), {
				stopReason: "error",
				errorMessage: "prompt is too long: 250000 tokens > 200000 maximum",
			}),
			say("summary"),
			say("prefix"),
			say("after the retry"),
			say("ack"),
		]);
		await s.session.prompt("overflow me", { expandPromptTemplates: false, source: "interactive" });
		await waitFor(() => s.rec.count("agent_settled") >= 2, { label: "settled" });
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const runs = named(spans, "pi.run");
		expect(runs.map((r) => r.attributes["pi.run.trigger"])).toEqual(["prompt", "prompt", "continuation"]);
		const failed = entryOf(
			s,
			(e) => e.type === "message" && e.message.role === "assistant" && e.message.stopReason === "error",
		);
		expect(failed).toHaveLength(1);
		const [overflowTurn] = children(spans, runs[1]);
		expect(overflowTurn.status).toEqual({ code: 2, message: failed[0].message.errorMessage });
		const [overflowChat] = children(spans, overflowTurn);
		expect(overflowChat.attributes["pi.session.entry_id"]).toBe(failed[0].id);
		expect(runs[1].status).toEqual({ code: 1 });
		const [entry] = entryOf(s, (e) => e.type === "compaction");
		const compactions = named(spans, "pi.compaction");
		expect(compactions).toHaveLength(1);
		expect(compactions[0].attributes).toMatchObject({
			"pi.compaction.reason": "overflow",
			"pi.compaction.will_retry": true,
			"pi.session.entry_id": entry.id,
		});
		expect(compactions[0].start).toBeGreaterThanOrEqual(runs[1].end);
		expect(compactions[0].end).toBeLessThanOrEqual(runs[2].start);
		expect(runs[2].attributes["pi.run.after_compaction"]).toBe(entry.id);
		expect("pi.session.entry_id" in runs[2].attributes).toBe(false);
		expect(runs[2].attributes["pi.run.turn_count"]).toBe(1);
		expect(runs[2].status).toEqual({ code: 1 });
		const [retryChat] = children(spans, children(spans, runs[2])[0]);
		expect(retryChat.status).toEqual({ code: 1 });
	});

	it("a child pi spawned by a tool joins the parent's trace under that tool span through PI_AGENT_TRACE_PARENT", async () => {
		const s = await live("subagent");
		const box = s.box;
		const envBefore = { ...process.env };
		const out = join(box.root, "child.json");
		await prompt(
			s,
			[
				toolCall("spawn_child", { sessionDir: box.sessionDir, cwd: box.cwd, agentDir: box.agentDir, out }),
				say("child finished"),
			],
			"delegate",
		);
		// Whatever carried the context to the child, the environment is back to what it was once no tool runs.
		expect(process.env).toEqual(envBefore);
		const { spans, problems } = trace(s);
		expect(problems).toEqual([]);
		const [tool] = named(spans, "execute_tool");
		expect(tool.status).toEqual({ code: 1 });
		const details = s.rec.lastResult("spawn_child").result as { details: { status: number | null } };
		expect(details.details.status).toBe(0);

		const child = JSON.parse(readFileSync(out, "utf8"));
		expect(child.sessionId).not.toBe(s.sessionManager.getSessionId());
		const childFile = join(child.sessionDir, "traces", `${child.sessionId}.otlp.jsonl`);
		const childTrace = readTrace(childFile);
		expect(childTrace.errors).toEqual([]);
		expect(liveProblems(childTrace.all, tool.spanId)).toEqual([]);
		expect(childTrace.spans.map((x) => x.name)).toEqual([
			"chat at-child-model",
			"execute_tool echo",
			"pi.turn",
			"chat at-child-model",
			"pi.turn",
			"pi.run",
		]);
		for (const span of childTrace.spans) {
			expect(span.traceId).toBe(tool.traceId);
			expect(span.resource["pi.session.id"]).toBe(child.sessionId);
		}
		const [childRun] = named(childTrace.spans, "pi.run");
		expect(childRun.parentSpanId).toBe(tool.spanId);
		// Two processes, two clocks: compare at millisecond granularity.
		expect(ms(childRun.start)).toBeGreaterThanOrEqual(ms(tool.start));
		expect(ms(childRun.end)).toBeLessThanOrEqual(ms(tool.end));
		// The child's own bijection holds against its own branch (from the session file it wrote).
		const childBranch = readFileSync(child.sessionFile, "utf8")
			.split("\n")
			.filter(Boolean)
			.map((line) => JSON.parse(line))
			.filter((e) => e.type === "message" || e.type === "custom_message" || e.type === "compaction");
		expect(traceProblems(childTrace.spans, [], childBranch, child.sessionId, tool.spanId)).toEqual([]);
		// Every root span of the child (its run) hangs under the parent's tool span; nothing else does.
		for (const span of childTrace.spans) {
			if (span.name === "pi.run") expect(span.parentSpanId).toBe(tool.spanId);
			else expect(span.parentSpanId).not.toBe(tool.spanId);
		}
	});
});
