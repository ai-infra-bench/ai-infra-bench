/**
 * Verifier-owned harness for the agent-trace contract.
 *
 * Drives a real AgentSession through pi's public SDK with the first-party faux
 * provider, loads the candidate extension through DefaultResourceLoader, and
 * records the session event stream and every provider request context. It
 * never imports candidate code directly.
 *
 * This file is copied into packages/coding-agent/test/__verifier__/ at verify
 * time, so relative imports point at the workspace source tree.
 */
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Context } from "@earendil-works/pi-ai";
import {
	type FauxProviderHandle,
	type FauxResponseStep,
	fauxAssistantMessage,
	fauxProvider,
	fauxText,
	fauxToolCall,
} from "@earendil-works/pi-ai/providers/faux";
import { Type } from "typebox";
import type { AgentSession, AgentSessionEvent } from "../../src/core/agent-session.ts";
import { type AgentSessionRuntime, createAgentSessionRuntime } from "../../src/core/agent-session-runtime.ts";
import { createAgentSessionServices } from "../../src/core/agent-session-services.ts";
import type { ExtensionAPI, ExtensionCommandContext, InlineExtension } from "../../src/core/extensions/types.ts";
import { DefaultResourceLoader } from "../../src/core/resource-loader.ts";
import { createAgentSession, createAgentSessionFromServices } from "../../src/core/sdk.ts";
import type { SessionEntry } from "../../src/core/session-manager.ts";
import { SessionManager } from "../../src/core/session-manager.ts";
import { SettingsManager } from "../../src/core/settings-manager.ts";

export const WORKSPACE = process.env.PI_WORKSPACE ?? "/workspace/pi";
export const EXTENSION_PATH = join(WORKSPACE, "packages/coding-agent/examples/extensions/agent-trace/index.ts");
export const FIXTURES = process.env.PI_VERIFIER_FIXTURES ?? "/tests/fixtures";
export const SCOPE_NAME = "pi.agent-trace";
export const TRACE_ID = /^[0-9a-f]{32}$/;
export const SPAN_ID = /^[0-9a-f]{16}$/;

export interface ToolCallRecord {
	toolName: string;
	result: unknown;
	isError: boolean;
}

export interface Recorder {
	events: AgentSessionEvent[];
	toolCalls: ToolCallRecord[];
	count: (type: AgentSessionEvent["type"]) => number;
	toolResults: (toolName: string) => ToolCallRecord[];
	lastResult: (toolName: string) => ToolCallRecord;
	unsubscribe: () => void;
}

export function record(session: AgentSession): Recorder {
	const events: AgentSessionEvent[] = [];
	const toolCalls: ToolCallRecord[] = [];
	const unsubscribe = session.subscribe((event) => {
		events.push(event);
		if (event.type === "tool_execution_end") {
			toolCalls.push({ toolName: event.toolName, result: event.result, isError: event.isError });
		}
	});
	return {
		events,
		toolCalls,
		count: (type) => events.filter((event) => event.type === type).length,
		toolResults: (toolName) => toolCalls.filter((call) => call.toolName === toolName),
		lastResult: (toolName) => {
			const calls = toolCalls.filter((call) => call.toolName === toolName);
			if (calls.length === 0) throw new Error(`no tool result recorded for ${toolName}`);
			return calls[calls.length - 1]!;
		},
		unsubscribe,
	};
}

/** The plain text of a tool result, error or not. */
export function rawText(call: ToolCallRecord): string {
	const message = call.result as { content: Array<{ type: string; text?: string }> };
	return message.content.map((block) => block.text ?? "").join("\n");
}

export function toolCall(name: string, args: Record<string, unknown>, id?: string) {
	return fauxAssistantMessage(fauxToolCall(name, args, id ? { id } : {}), { stopReason: "toolUse" });
}

export function say(text: string) {
	return fauxAssistantMessage(fauxText(text));
}

export function withAcks(steps: FauxResponseStep[], count = 4): FauxResponseStep[] {
	const acks: FauxResponseStep[] = [];
	for (let i = 0; i < count; i += 1) acks.push(say(`ack ${i + 1}`));
	return [...steps, ...acks];
}

export interface Sandbox {
	root: string;
	cwd: string;
	agentDir: string;
	sessionDir: string;
	cleanup: () => void;
}

export function sandbox(): Sandbox {
	const root = mkdtempSync(join(tmpdir(), "pi-hn-verifier-"));
	const cwd = join(root, "project");
	const agentDir = join(root, "agent");
	const sessionDir = join(root, "sessions");
	for (const dir of [cwd, agentDir, sessionDir]) mkdirSync(dir, { recursive: true });
	return { root, cwd, agentDir, sessionDir, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

export const CONTEXT_WINDOW_TOKENS = 200_000;

/** `tokensPerSecond` slows the faux stream down so a case can abort or shut down mid-stream. */
export function newFaux(
	tag: string,
	contextWindow = CONTEXT_WINDOW_TOKENS,
	tokensPerSecond?: number,
): FauxProviderHandle {
	return fauxProvider({
		provider: `hn-verifier-${tag}`,
		api: `hn-verifier-api-${tag}`,
		models: [{ id: `hn-verifier-model-${tag}`, contextWindow, maxTokens: 8_192 }],
		tokensPerSecond,
	});
}

export interface VerifierExtension {
	name: string;
	factory: (pi: ExtensionAPI) => void;
	api: () => ExtensionAPI;
	/** When true, the next agent_end queues one follow-up message (a continuation run). */
	state: { queueFollowUp: boolean; turnStarts: number[]; compactFailures: string[] };
}

/**
 * Verifier-side inline extension: registers the faux provider, an `echo` tool
 * with known text, a `boom` tool that fails, and an agent_end hook that can
 * queue a follow-up so pi continues the run.
 */
export function verifierExtension(faux: FauxProviderHandle, tag: string): VerifierExtension {
	let current: ExtensionAPI | undefined;
	const state = { queueFollowUp: false, turnStarts: [] as number[], compactFailures: [] as string[] };
	return {
		name: `at-verifier-${tag}`,
		state,
		api: () => {
			if (!current) throw new Error("verifier extension not loaded");
			return current;
		},
		factory: (pi: ExtensionAPI) => {
			current = pi;
			pi.registerProvider(faux.provider);
			pi.registerTool({
				name: "echo",
				label: "Echo",
				description: "Verifier tool that returns its text argument after a short delay.",
				parameters: Type.Object({ text: Type.String(), delayMs: Type.Optional(Type.Number()) }),
				async execute(_id: string, params: { text: string; delayMs?: number }) {
					if (params.delayMs) await sleep(params.delayMs);
					return { content: [{ type: "text", text: params.text }], details: { length: params.text.length } };
				},
			});
			pi.registerTool({
				name: "spawn_child",
				label: "Spawn child pi",
				description:
					"Verifier tool that runs a child pi process (a sub-agent) with the current environment and waits for it.",
				parameters: Type.Object({
					sessionDir: Type.String(),
					cwd: Type.String(),
					agentDir: Type.String(),
					out: Type.String(),
				}),
				async execute(_id: string, params: { sessionDir: string; cwd: string; agentDir: string; out: string }) {
					const child = join(WORKSPACE, "packages/coding-agent/test/__verifier__/pi_child.mjs");
					mkdirSync(join(WORKSPACE, "packages/coding-agent/test/__verifier__"), { recursive: true });
					copyFileSync(join(FIXTURES, "pi_child.mjs"), child);
					const result = spawnSync(
						process.execPath,
						[child, "child-run", params.sessionDir, params.cwd, params.agentDir, params.out],
						{
							cwd: join(WORKSPACE, "packages/coding-agent"),
							env: {
								...process.env,
								PI_WORKSPACE: WORKSPACE,
								PI_VERIFIER_FIXTURES: FIXTURES,
								PI_OFFLINE: "1",
								PI_TELEMETRY: "0",
								PI_NO_LOCAL_LLM: "1",
								NODE_OPTIONS: "",
							},
							encoding: "utf8",
							timeout: 60_000,
						},
					);
					const text = `child exited ${result.status}\n${result.stdout}${result.stderr}`;
					return {
						content: [{ type: "text", text }],
						details: { status: result.status },
					};
				},
			});
			pi.registerTool({
				name: "boom",
				label: "Boom",
				description: "Verifier tool that always fails.",
				parameters: Type.Object({ reason: Type.String() }),
				async execute(_id: string, params: { reason: string }) {
					throw new Error(`boom: ${params.reason}`);
				},
			});
			pi.on("turn_start", async (event) => {
				state.turnStarts.push(event.timestamp);
			});
			pi.on("session_compact_failed", async (event) => {
				state.compactFailures.push(event.errorMessage ?? "");
			});
			pi.on("agent_end", async () => {
				if (!state.queueFollowUp) return;
				state.queueFollowUp = false;
				pi.sendMessage(
					{ customType: "at-verifier-followup", content: "keep going", display: false },
					{ deliverAs: "followUp" },
				);
			});
			pi.registerCommand("at-verifier-reload", {
				description: "Verifier command that runs the same flow as /reload",
				handler: async (_args: string, ctx: ExtensionCommandContext) => {
					await ctx.reload();
				},
			});
		},
	};
}

export function loaderOptions(ext: VerifierExtension) {
	const additionalExtensionPaths = existsSync(EXTENSION_PATH) ? [EXTENSION_PATH] : [];
	const inline: InlineExtension = { name: ext.name, factory: ext.factory };
	return {
		additionalExtensionPaths,
		extensionFactories: [inline],
		noExtensions: true,
		noSkills: true,
		noPromptTemplates: true,
		noThemes: true,
		noContextFiles: true,
		systemPrompt: "You are a deterministic verifier session.",
	};
}

/** Manual compaction needs something to summarize even in short sessions; automatic compaction stays out of reach unless a case shrinks the context window. */
export function settings() {
	return SettingsManager.inMemory({
		compaction: { enabled: true, keepRecentTokens: 1, reserveTokens: 16_384 },
		retry: { enabled: false },
	});
}

export interface Live {
	session: AgentSession;
	faux: FauxProviderHandle;
	ext: VerifierExtension;
	rec: Recorder;
	box: Sandbox;
	sessionManager: SessionManager;
	settingsManager: SettingsManager;
	/** Every provider request context, in order (system prompt + messages as sent). */
	requests: Context[];
	dispose: () => Promise<void>;
}

export async function startSession(
	tag: string,
	options: { box?: Sandbox; sessionManager?: SessionManager; contextWindow?: number; tokensPerSecond?: number } = {},
): Promise<Live> {
	const box = options.box ?? sandbox();
	const faux = newFaux(tag, options.contextWindow, options.tokensPerSecond);
	const ext = verifierExtension(faux, tag);
	const settingsManager = settings();
	const resourceLoader = new DefaultResourceLoader({
		cwd: box.cwd,
		agentDir: box.agentDir,
		settingsManager,
		...loaderOptions(ext),
	});
	await resourceLoader.reload();
	const sessionManager = options.sessionManager ?? SessionManager.create(box.cwd, box.sessionDir);
	const { session } = await createAgentSession({
		cwd: box.cwd,
		agentDir: box.agentDir,
		model: faux.getModel(),
		thinkingLevel: "off",
		noTools: "builtin",
		resourceLoader,
		sessionManager,
		settingsManager,
	});
	await session.bindExtensions({});
	const rec = record(session);
	return {
		session,
		faux,
		ext,
		rec,
		box,
		sessionManager,
		settingsManager,
		requests: [],
		dispose: async () => {
			rec.unsubscribe();
			session.dispose();
		},
	};
}

export interface LiveRuntime {
	runtime: AgentSessionRuntime;
	faux: FauxProviderHandle;
	box: Sandbox;
	requests: Context[];
	rebind: () => Promise<Recorder>;
	dispose: () => Promise<void>;
}

/** Session-replacement runtime (the same machinery behind /new, /fork, /resume). */
export async function startRuntime(tag: string, box = sandbox(), tokensPerSecond?: number): Promise<LiveRuntime> {
	const faux = newFaux(tag, undefined, tokensPerSecond);
	const ext = verifierExtension(faux, tag);
	const settingsManager = settings();
	const runtime = await createAgentSessionRuntime(
		async ({ cwd, sessionManager, sessionStartEvent }) => {
			const services = await createAgentSessionServices({
				cwd,
				agentDir: box.agentDir,
				settingsManager,
				resourceLoaderOptions: loaderOptions(ext),
			});
			return {
				...(await createAgentSessionFromServices({
					services,
					sessionManager,
					sessionStartEvent,
					model: faux.getModel(),
					thinkingLevel: "off",
					noTools: "builtin",
				})),
				services,
				diagnostics: services.diagnostics,
			};
		},
		{ cwd: box.cwd, agentDir: box.agentDir, sessionManager: SessionManager.create(box.cwd, box.sessionDir) },
	);
	let rec: Recorder | undefined;
	const rebind = async () => {
		rec?.unsubscribe();
		await runtime.session.bindExtensions({});
		rec = record(runtime.session);
		return rec;
	};
	return {
		runtime,
		faux,
		box,
		requests: [],
		rebind,
		dispose: async () => {
			rec?.unsubscribe();
			// Not runtime.dispose(): that announces a process-level quit.
			runtime.session.dispose();
		},
	};
}

/** Wrap scripted responses so every provider request context is captured. */
function capturing(steps: FauxResponseStep[], requests: Context[]): FauxResponseStep[] {
	return steps.map((step) =>
		typeof step === "function"
			? step
			: (context: Context) => {
					requests.push({ systemPrompt: context.systemPrompt, messages: structuredClone(context.messages) });
					return step;
				},
	);
}

export async function prompt(
	live: { session: AgentSession; faux: FauxProviderHandle; requests: Context[] },
	steps: FauxResponseStep[],
	text = "go",
) {
	live.faux.setResponses(capturing(withAcks(steps), live.requests));
	await live.session.prompt(text, { expandPromptTemplates: false, source: "interactive" });
}

/** Manual compaction: pi asks the model for the summary and the turn-prefix summary. */
export async function compact(
	live: { session: AgentSession; faux: FauxProviderHandle; requests: Context[] },
	label = "summary",
) {
	live.faux.setResponses(
		capturing([say(`${label} of the earlier window`), say(`${label} turn prefix`)], live.requests),
	);
	await live.session.compact();
}

export async function waitFor<T>(
	probe: () => T | undefined | false,
	{ timeoutMs = 4000, intervalMs = 25, label = "condition" } = {},
): Promise<T> {
	const deadline = Date.now() + timeoutMs;
	for (;;) {
		const value = probe();
		if (value) return value;
		if (Date.now() > deadline) throw new Error(`timed out waiting for ${label}`);
		await sleep(intervalMs);
	}
}

export const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// ---------------------------------------------------------------------------
// Trace file
// ---------------------------------------------------------------------------

export interface Span {
	line: number;
	/** "start" for a live start line (no end time, no status), "end" for a finished span. */
	phase: "start" | "end";
	traceId: string;
	spanId: string;
	parentSpanId: string | null;
	name: string;
	kind: number;
	start: bigint;
	end: bigint;
	attributes: Record<string, string | number | boolean | string[]>;
	status: { code: number; message?: string };
	resource: Record<string, string | number | boolean | string[]>;
	scope: { name: string; version: string };
}

export function traceFileFor(sessionManager: Pick<SessionManager, "getSessionDir" | "getSessionId">): string {
	return join(sessionManager.getSessionDir(), "traces", `${sessionManager.getSessionId()}.otlp.jsonl`);
}

function decodeAttributes(
	raw: unknown,
	where: string,
	errors: string[],
): Record<string, string | number | boolean | string[]> {
	const out: Record<string, string | number | boolean | string[]> = {};
	if (!Array.isArray(raw)) {
		errors.push(`${where}: attributes is not an array`);
		return out;
	}
	for (const item of raw) {
		if (
			!item ||
			typeof item !== "object" ||
			typeof item.key !== "string" ||
			!item.value ||
			typeof item.value !== "object"
		) {
			errors.push(`${where}: malformed attribute ${JSON.stringify(item)}`);
			continue;
		}
		if (item.key in out) errors.push(`${where}: attribute ${item.key} appears twice`);
		const keys = Object.keys(item.value);
		if (keys.length !== 1) {
			errors.push(`${where}: attribute ${item.key} value must have exactly one field`);
			continue;
		}
		const [field] = keys;
		const value = item.value[field];
		if (field === "stringValue" && typeof value === "string") out[item.key] = value;
		else if (field === "boolValue" && typeof value === "boolean") out[item.key] = value;
		else if (field === "intValue" && typeof value === "string" && /^-?\d+$/.test(value))
			out[item.key] = Number(value);
		else if (
			field === "arrayValue" &&
			value &&
			typeof value === "object" &&
			Array.isArray(value.values) &&
			value.values.every(
				(v: any) => v && typeof v === "object" && typeof v.stringValue === "string" && Object.keys(v).length === 1,
			)
		)
			out[item.key] = value.values.map((v: any) => v.stringValue as string);
		else errors.push(`${where}: attribute ${item.key} has an invalid ${field}: ${JSON.stringify(value)}`);
	}
	return out;
}

/** Parse the trace file strictly against the OTLP/JSON shape the contract fixes. */
/** Parse the trace file strictly: `spans` are the end lines (finished spans), `starts` the live start lines. */
export function readTrace(file: string): { spans: Span[]; starts: Span[]; all: Span[]; errors: string[] } {
	const spans: Span[] = [];
	const starts: Span[] = [];
	const all: Span[] = [];
	const errors: string[] = [];
	if (!existsSync(file)) return { spans, starts, all, errors: [`trace file ${file} does not exist`] };
	const text = readFileSync(file, "utf8");
	if (text.length > 0 && !text.endsWith("\n")) errors.push("trace file does not end with a newline");
	const lines = text.split("\n");
	if (lines[lines.length - 1] === "") lines.pop();
	lines.forEach((line, index) => {
		const where = `line ${index + 1}`;
		let parsed: any;
		try {
			parsed = JSON.parse(line);
		} catch {
			errors.push(`${where}: not JSON`);
			return;
		}
		const rs = parsed?.resourceSpans;
		if (!Array.isArray(rs) || rs.length !== 1 || Object.keys(parsed).length !== 1) {
			errors.push(`${where}: expected exactly one resourceSpans entry`);
			return;
		}
		const resource = decodeAttributes(rs[0]?.resource?.attributes, `${where} resource`, errors);
		const ss = rs[0]?.scopeSpans;
		if (!Array.isArray(ss) || ss.length !== 1) {
			errors.push(`${where}: expected exactly one scopeSpans entry`);
			return;
		}
		const scope = ss[0]?.scope ?? {};
		if (scope.name !== SCOPE_NAME || scope.version !== "1") errors.push(`${where}: scope must be ${SCOPE_NAME}/1`);
		const raw = ss[0]?.spans;
		if (!Array.isArray(raw) || raw.length !== 1) {
			errors.push(`${where}: expected exactly one span`);
			return;
		}
		const s = raw[0];
		if (typeof s.traceId !== "string" || !TRACE_ID.test(s.traceId)) errors.push(`${where}: bad traceId`);
		if (typeof s.spanId !== "string" || !SPAN_ID.test(s.spanId)) errors.push(`${where}: bad spanId`);
		if ("parentSpanId" in s && (typeof s.parentSpanId !== "string" || !SPAN_ID.test(s.parentSpanId)))
			errors.push(`${where}: bad parentSpanId`);
		if (typeof s.name !== "string" || s.name.length === 0) errors.push(`${where}: bad name`);
		if (s.kind !== 1 && s.kind !== 3) errors.push(`${where}: kind must be 1 or 3`);
		const attributes = decodeAttributes(s.attributes, where, errors);
		const phase: "start" | "end" = "endTimeUnixNano" in s || "status" in s ? "end" : "start";
		if (typeof s.startTimeUnixNano !== "string" || !/^\d+$/.test(s.startTimeUnixNano))
			errors.push(`${where}: startTimeUnixNano must be a decimal string`);
		let start = 0n;
		let end = 0n;
		try {
			start = BigInt(s.startTimeUnixNano);
		} catch {
			// reported above
		}
		if (phase === "start") {
			if (attributes["pi.span.phase"] !== "start") errors.push(`${where}: a start line needs pi.span.phase = start`);
		} else {
			if (typeof s.endTimeUnixNano !== "string" || !/^\d+$/.test(s.endTimeUnixNano))
				errors.push(`${where}: endTimeUnixNano must be a decimal string`);
			const status = s.status;
			if (!status || typeof status !== "object" || (status.code !== 1 && status.code !== 2))
				errors.push(`${where}: status.code must be 1 or 2`);
			else if (status.code === 2 && typeof status.message !== "string")
				errors.push(`${where}: ERROR status needs a message`);
			else if ("message" in status && typeof status.message !== "string")
				errors.push(`${where}: status.message must be a string`);
			if ("pi.span.phase" in attributes) errors.push(`${where}: an end line must not carry pi.span.phase`);
			try {
				end = BigInt(s.endTimeUnixNano);
			} catch {
				// reported above
			}
			if (start > end) errors.push(`${where}: start after end`);
		}
		const status = s.status;
		const span: Span = {
			line: index + 1,
			phase,
			traceId: String(s.traceId),
			spanId: String(s.spanId),
			parentSpanId: typeof s.parentSpanId === "string" ? s.parentSpanId : null,
			name: String(s.name),
			kind: s.kind,
			start,
			end,
			attributes,
			status: status && typeof status === "object" ? status : { code: 0 },
			resource,
			scope: { name: String(scope.name), version: String(scope.version) },
		};
		all.push(span);
		(phase === "start" ? starts : spans).push(span);
	});
	return { spans, starts, all, errors };
}

/** Live-update invariants: every end line has exactly one earlier start line that it agrees with; parents start before children. */
export function liveProblems(all: Span[], externalParent?: string): string[] {
	const problems: string[] = [];
	const startOf = new Map<string, Span>();
	const endOf = new Map<string, Span>();
	for (const span of all) {
		const map = span.phase === "start" ? startOf : endOf;
		if (map.has(span.spanId)) problems.push(`line ${span.line}: second ${span.phase} line for ${span.spanId}`);
		map.set(span.spanId, span);
	}
	for (const end of endOf.values()) {
		const start = startOf.get(end.spanId);
		if (!start) {
			problems.push(`line ${end.line}: end line without a start line`);
			continue;
		}
		if (start.line > end.line) problems.push(`line ${end.line}: start line written after the end line`);
		for (const field of ["traceId", "parentSpanId", "name", "kind"] as const) {
			if (start[field] !== end[field]) problems.push(`line ${end.line}: ${field} differs from the start line`);
		}
		if (start.start !== end.start) problems.push(`line ${end.line}: startTimeUnixNano differs from the start line`);
		for (const [key, value] of Object.entries(start.attributes)) {
			if (key === "pi.span.phase") continue;
			if (JSON.stringify(end.attributes[key]) !== JSON.stringify(value))
				problems.push(`line ${end.line}: start-line attribute ${key} missing or changed on the end line`);
		}
	}
	for (const start of startOf.values()) {
		if (!start.parentSpanId || start.parentSpanId === externalParent) continue;
		const parent = startOf.get(start.parentSpanId);
		if (!parent) problems.push(`line ${start.line}: parent ${start.parentSpanId} has no start line`);
		else if (parent.line > start.line)
			problems.push(`line ${start.line}: child started before its parent's start line`);
	}
	return problems;
}

/** Whole milliseconds of a nanosecond timestamp. */
export const ms = (nanos: bigint): bigint => nanos / 1_000_000n;
// Order between two spans: `later` is at or after `earlier`, decided at millisecond granularity with
// 1 ms of tolerance. The contract mixes clocks by construction: a turn starts at pi's `turn_start`
// event timestamp (whole milliseconds, Date.now), every other timestamp comes from "the clock" with
// sub-millisecond digits left to the implementation. A monotonic clock anchored to Date.now() at
// startup lags it by up to 1 ms, so two correct timestamps of adjacent events can be inverted by a
// fraction of a millisecond, across a millisecond boundary (seen 2026-09-20: a compaction start of
// ...154.799 ms against a run end of ...155.000 ms on the claude-opus-5 submission).
export const atOrAfter = (later: bigint, earlier: bigint): boolean => ms(later) + 1n >= ms(earlier);

export function children(spans: Span[], parent: Span): Span[] {
	return spans.filter((span) => span.parentSpanId === parent.spanId);
}

export function named(spans: Span[], prefix: string): Span[] {
	return spans.filter((span) => span.name === prefix || span.name.startsWith(`${prefix} `));
}

/** Contract-wide invariants: encoding, ids, nesting, ordering, and the bijection with the session branch. */
/** `externalParent`: the span id a sub-agent's root spans hang under; it lives in the parent process's file. */
export function traceProblems(
	spans: Span[],
	errors: string[],
	branch: SessionEntry[],
	sessionId: string,
	externalParent?: string,
): string[] {
	const problems = [...errors];
	const ids = new Set<string>();
	const byId = new Map<string, Span>();
	for (const span of spans) {
		if (ids.has(span.spanId)) problems.push(`duplicate spanId ${span.spanId}`);
		ids.add(span.spanId);
		byId.set(span.spanId, span);
		if (span.resource["service.name"] !== "pi") problems.push(`line ${span.line}: service.name`);
		if (typeof span.resource["service.version"] !== "string") problems.push(`line ${span.line}: service.version`);
		if (span.resource["pi.session.id"] !== sessionId) problems.push(`line ${span.line}: pi.session.id`);
		if (typeof span.resource["process.pid"] !== "number") problems.push(`line ${span.line}: process.pid`);
	}
	const traceIds = new Set(spans.map((span) => span.traceId));
	if (traceIds.size > 1) problems.push(`more than one traceId: ${[...traceIds].join(",")}`);
	for (let i = 1; i < spans.length; i++) {
		if (spans[i].end < spans[i - 1].end) problems.push(`line ${spans[i].line}: endTimeUnixNano decreased`);
	}
	for (const span of spans) {
		if (!span.parentSpanId || span.parentSpanId === externalParent) continue;
		const parent = byId.get(span.parentSpanId);
		if (!parent) {
			problems.push(`line ${span.line}: parent ${span.parentSpanId} not in file`);
			continue;
		}
		// Cross-span time comparisons go through atOrAfter (millisecond granularity, 1 ms tolerance):
		// sub-millisecond digits are the implementation's own and never decide an order.
		if (!atOrAfter(span.start, parent.start) || !atOrAfter(parent.end, span.end))
			problems.push(`line ${span.line}: ${span.name} not nested in ${parent.name}`);
	}
	// Turns of a run do not overlap; tools start after the chat of their turn ends.
	for (const run of named(spans, "pi.run")) {
		const turns = children(spans, run).sort((a, b) => (a.start < b.start ? -1 : 1));
		for (let i = 1; i < turns.length; i++) {
			if (!atOrAfter(turns[i].start, turns[i - 1].end)) problems.push(`run ${run.spanId}: turns overlap`);
		}
		for (const turn of turns) {
			const kids = children(spans, turn);
			const chats = kids.filter((k) => k.name.startsWith("chat "));
			const tools = kids.filter((k) => k.name.startsWith("execute_tool "));
			if (chats.length !== 1) problems.push(`turn ${turn.spanId}: ${chats.length} chat spans`);
			for (const tool of tools)
				if (chats[0] && !atOrAfter(tool.start, chats[0].end)) problems.push(`turn ${turn.spanId}: tool before chat ended`);
			if (kids.length !== chats.length + tools.length) problems.push(`turn ${turn.spanId}: unexpected child kinds`);
		}
		if (run.attributes["pi.run.turn_count"] !== turns.length)
			problems.push(`run ${run.spanId}: turn_count ${run.attributes["pi.run.turn_count"]} != ${turns.length}`);
	}
	// Bijection with the session branch.
	// A span closed by a shutdown whose entry pi never persisted has no entry id and is exempt from the bijection.
	const live = spans.filter((span) => span.status.message !== "shutdown" || "pi.session.entry_id" in span.attributes);
	const refs = (prefix: string) => named(live, prefix).map((span) => span.attributes["pi.session.entry_id"]);
	const expectRefs = (label: string, actual: unknown[], expected: string[]) => {
		const a = [...actual].map(String).sort();
		const e = [...expected].sort();
		if (JSON.stringify(a) !== JSON.stringify(e))
			problems.push(`${label}: spans reference ${JSON.stringify(a)} but the branch has ${JSON.stringify(e)}`);
	};
	const entries = (pred: (entry: SessionEntry) => boolean) => branch.filter(pred).map((entry) => entry.id);
	expectRefs(
		"chat",
		refs("chat"),
		entries((e) => e.type === "message" && e.message.role === "assistant"),
	);
	expectRefs(
		"execute_tool",
		refs("execute_tool"),
		entries((e) => e.type === "message" && e.message.role === "toolResult"),
	);
	expectRefs(
		"pi.compaction (ok)",
		named(live, "pi.compaction")
			.filter((s) => s.status.code === 1)
			.map((s) => s.attributes["pi.session.entry_id"]),
		entries((e) => e.type === "compaction"),
	);
	for (const s of named(spans, "pi.compaction").filter((s) => s.status.code === 2)) {
		if ("pi.session.entry_id" in s.attributes || "pi.compaction.tokens_before" in s.attributes)
			problems.push(`line ${s.line}: failed compaction carries an entry id or tokens_before`);
	}
	const runs = named(live, "pi.run");
	// User entries: the prompt runs' entry ids plus every steering id, each once.
	const steerIds = runs.flatMap((r) =>
		Array.isArray(r.attributes["pi.run.steer_entry_ids"]) ? (r.attributes["pi.run.steer_entry_ids"] as string[]) : [],
	);
	for (const r of runs) {
		const ids = r.attributes["pi.run.steer_entry_ids"];
		if (!Array.isArray(ids)) problems.push(`run ${r.spanId}: pi.run.steer_entry_ids missing or not a string array`);
		if (r.attributes["pi.run.steer_count"] !== (Array.isArray(ids) ? ids.length : -1))
			problems.push(`run ${r.spanId}: pi.run.steer_count does not match steer_entry_ids`);
	}
	const customIdSet = new Set(entries((e) => e.type === "custom_message"));
	const userSteerIds = steerIds.filter((id) => !customIdSet.has(id));
	const customSteerIds = steerIds.filter((id) => customIdSet.has(id));
	expectRefs(
		"pi.run (prompt) + user steering",
		[
			...runs
				.filter((r) => r.attributes["pi.run.trigger"] === "prompt")
				.map((r) => r.attributes["pi.session.entry_id"]),
			...userSteerIds,
		],
		entries((e) => e.type === "message" && e.message.role === "user"),
	);
	const customIds = customIdSet;
	const overflowCompactions = new Set(
		named(spans, "pi.compaction")
			.filter((s) => s.status.code === 1 && s.attributes["pi.compaction.will_retry"] === true)
			.map((s) => s.attributes["pi.session.entry_id"]),
	);
	const retryRuns = runs.filter((r) => "pi.run.after_compaction" in r.attributes);
	for (const r of retryRuns) {
		if (r.attributes["pi.run.trigger"] !== "continuation")
			problems.push(`run ${r.spanId}: after_compaction on a ${r.attributes["pi.run.trigger"]} run`);
		if ("pi.session.entry_id" in r.attributes)
			problems.push(`run ${r.spanId}: an overflow retry run must not reference a message`);
		if (!overflowCompactions.has(r.attributes["pi.run.after_compaction"]))
			problems.push(`run ${r.spanId}: after_compaction is not a will_retry compaction entry`);
	}
	const otherRuns = runs.filter(
		(r) => r.attributes["pi.run.trigger"] !== "prompt" && !("pi.run.after_compaction" in r.attributes),
	);
	const seen = new Set<string>(customSteerIds);
	if (seen.size !== customSteerIds.length) problems.push("a custom message is listed twice as a steering message");
	for (const r of otherRuns) {
		const id = String(r.attributes["pi.session.entry_id"]);
		if (!customIds.has(id)) problems.push(`run ${r.spanId}: entry ${id} is not a custom message on the branch`);
		if (seen.has(id)) problems.push(`run ${r.spanId}: entry ${id} referenced twice`);
		seen.add(id);
		if (!["wakeup", "continuation"].includes(String(r.attributes["pi.run.trigger"])))
			problems.push(`run ${r.spanId}: unknown trigger`);
	}
	return problems;
}

/** Text of every custom message with the given customType on the current branch, in order. */
export function customTexts(sessionManager: Pick<SessionManager, "getBranch">, customType: string): string[] {
	return sessionManager.getBranch().flatMap((entry: SessionEntry) => {
		if (entry.type !== "custom_message" || entry.customType !== customType) return [];
		const content = entry.content;
		if (typeof content === "string") return [content];
		return [content.flatMap((block) => (block.type === "text" ? [block.text] : [])).join("\n")];
	});
}

/** Text an LLM-facing message carries. */
export function messageText(message: { content: unknown }): string {
	const content = message.content;
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content.flatMap((block: any) => (block?.type === "text" ? [block.text as string] : [])).join("\n");
}

export function firstUserEntryId(sessionManager: SessionManager): string {
	for (const entry of sessionManager.getEntries()) {
		if (entry.type === "message" && entry.message.role === "user") return entry.id;
	}
	throw new Error("no user entry in session");
}
