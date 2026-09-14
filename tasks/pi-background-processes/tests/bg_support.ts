/**
 * Verifier-owned harness for the background-processes contract.
 *
 * Drives a real AgentSession through pi's public SDK with the first-party faux
 * provider, loads the candidate extension through DefaultResourceLoader, and
 * records the session event stream. It never imports candidate code directly.
 *
 * This file is copied into packages/coding-agent/test/__verifier__/ at verify
 * time, so relative imports point at the workspace source tree.
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import {
	fauxAssistantMessage,
	fauxProvider,
	fauxText,
	fauxToolCall,
	type FauxProviderHandle,
	type FauxResponseStep,
} from "@earendil-works/pi-ai/providers/faux";
import { Type } from "typebox";
import { type AgentSession, type AgentSessionEvent } from "../../src/core/agent-session.ts";
import { createAgentSessionRuntime, type AgentSessionRuntime } from "../../src/core/agent-session-runtime.ts";
import { createAgentSessionServices } from "../../src/core/agent-session-services.ts";
import type { ExtensionAPI, ExtensionCommandContext, InlineExtension } from "../../src/core/extensions/types.ts";
import { DefaultResourceLoader } from "../../src/core/resource-loader.ts";
import { createAgentSession, createAgentSessionFromServices } from "../../src/core/sdk.ts";
import type { SessionEntry } from "../../src/core/session-manager.ts";
import { SessionManager } from "../../src/core/session-manager.ts";
import { SettingsManager } from "../../src/core/settings-manager.ts";

export const WORKSPACE = process.env.PI_WORKSPACE ?? "/workspace/pi";
export const EXTENSION_PATH = join(
	WORKSPACE,
	"packages/coding-agent/examples/extensions/background-processes/index.ts",
);
export const FIXTURES = process.env.PI_VERIFIER_FIXTURES ?? "/tests/fixtures";
export const EMIT = join(FIXTURES, "emit.mjs");
export const WAKE_TYPE = "background-process";
export const BG_TOOLS = ["bg_run", "bg_logs", "bg_list", "bg_kill", "bg_watch"] as const;

export interface ToolCallRecord {
	toolName: string;
	args: unknown;
	result: unknown;
	isError: boolean;
	entryIndex: number;
}

export interface WakeRecord {
	entryIndex: number;
	details: {
		id: string;
		name: string;
		reasons: string[];
		exitCode: number | null;
		matchedLine: string | null;
	};
	content: string;
}

export interface Recorder {
	events: AgentSessionEvent[];
	entries: SessionEntry[];
	toolCalls: ToolCallRecord[];
	wakes: () => WakeRecord[];
	count: (type: AgentSessionEvent["type"]) => number;
	assistantTexts: () => Array<{ text: string; entryIndex: number }>;
	toolResults: (toolName: string) => ToolCallRecord[];
	lastResult: (toolName: string) => ToolCallRecord;
	unsubscribe: () => void;
}

export function record(session: AgentSession): Recorder {
	const events: AgentSessionEvent[] = [];
	const entries: SessionEntry[] = [];
	const toolCalls: ToolCallRecord[] = [];
	const unsubscribe = session.subscribe((event) => {
		events.push(event);
		if (event.type === "entry_appended") entries.push(event.entry);
		if (event.type === "tool_execution_end") {
			toolCalls.push({
				toolName: event.toolName,
				args: undefined,
				result: event.result,
				isError: event.isError,
				entryIndex: session.messages.length,
			});
		}
	});
	const wakes = () =>
		entries.flatMap((entry, entryIndex) => {
			if (entry.type !== "message" || entry.message.role !== "custom") return [];
			const message = entry.message as Extract<AgentMessage, { role: "custom" }>;
			if (message.customType !== WAKE_TYPE) return [];
			const content =
				typeof message.content === "string"
					? message.content
					: message.content.flatMap((block) => (block.type === "text" ? [block.text] : [])).join("\n");
			return [{ entryIndex, details: message.details as WakeRecord["details"], content }];
		});
	return {
		events,
		entries,
		toolCalls,
		wakes,
		count: (type) => events.filter((event) => event.type === type).length,
		assistantTexts: () =>
			entries.flatMap((entry, entryIndex) => {
				if (entry.type !== "message" || entry.message.role !== "assistant") return [];
				const text = entry.message.content
					.flatMap((block) => (block.type === "text" ? [block.text] : []))
					.join("");
				return text ? [{ text, entryIndex }] : [];
			}),
		toolResults: (toolName) => toolCalls.filter((call) => call.toolName === toolName),
		lastResult: (toolName) => {
			const calls = toolCalls.filter((call) => call.toolName === toolName);
			if (calls.length === 0) throw new Error(`no tool result recorded for ${toolName}`);
			return calls[calls.length - 1]!;
		},
		unsubscribe,
	};
}

/** The plain text of a tool result, error or not (for tools whose normal path is not JSON). */
export function rawText(call: ToolCallRecord): string {
	const message = call.result as { content: Array<{ type: string; text?: string }> };
	return message.content.map((block) => block.text ?? "").join("\n");
}

/** Parse a tool result into the structured object the contract requires. */
export function payload(call: ToolCallRecord): any {
	const message = call.result as { details?: unknown; content: Array<{ type: string; text?: string }> };
	if (call.isError) {
		const text = message.content.map((block) => block.text ?? "").join("\n");
		throw new Error(`tool ${call.toolName} returned an error: ${text}`);
	}
	if (message.details && typeof message.details === "object") return message.details;
	const text = message.content.flatMap((block) => (block.type === "text" && block.text ? [block.text] : [])).join("\n");
	return JSON.parse(text);
}

export function toolCall(name: string, args: Record<string, unknown>, id?: string) {
	return fauxAssistantMessage(fauxToolCall(name, args, id ? { id } : {}), { stopReason: "toolUse" });
}

export function say(text: string) {
	return fauxAssistantMessage(fauxText(text));
}

/** Enough trailing acknowledgements so wake-triggered turns never exhaust the script. */
export function withAcks(steps: FauxResponseStep[], count = 6): FauxResponseStep[] {
	const acks: FauxResponseStep[] = [];
	for (let i = 0; i < count; i += 1) acks.push(say(`ack ${i + 1}`));
	return [...steps, ...acks];
}

export function emitCommand(flags: string): string {
	return `${JSON.stringify(process.execPath)} ${JSON.stringify(EMIT)} ${flags}`;
}

export interface Sandbox {
	root: string;
	cwd: string;
	agentDir: string;
	sessionDir: string;
	file: (name: string) => string;
	cleanup: () => void;
}

export function sandbox(): Sandbox {
	const root = mkdtempSync(join(tmpdir(), "pi-bg-verifier-"));
	const cwd = join(root, "project");
	const agentDir = join(root, "agent");
	const sessionDir = join(root, "sessions");
	for (const dir of [cwd, agentDir, sessionDir]) mkdirSync(dir, { recursive: true });
	return {
		root,
		cwd,
		agentDir,
		sessionDir,
		file: (name) => join(root, name),
		cleanup: () => rmSync(root, { recursive: true, force: true }),
	};
}

export function newFaux(tag: string): FauxProviderHandle {
	return fauxProvider({
		provider: `bg-verifier-${tag}`,
		api: `bg-verifier-api-${tag}`,
		models: [{ id: `bg-verifier-model-${tag}`, contextWindow: 200_000, maxTokens: 8_192 }],
	});
}

export interface VerifierExtension {
	name: string;
	factory: (pi: ExtensionAPI) => void;
	api: () => ExtensionAPI;
}

/**
 * Verifier-side inline extension: registers the faux provider, a blocking
 * `slow_wait` tool used to hold the agent inside a tool batch, and a reload
 * command. It never touches process management.
 */
export function verifierExtension(faux: FauxProviderHandle, tag: string): VerifierExtension {
	let current: ExtensionAPI | undefined;
	return {
		name: `bg-verifier-${tag}`,
		api: () => {
			if (!current) throw new Error("verifier extension not loaded");
			return current;
		},
		factory: (pi: ExtensionAPI) => {
			current = pi;
			pi.registerProvider(faux.provider);
			pi.registerTool({
				name: "slow_wait",
				label: "Slow wait",
				description: "Verifier tool that blocks for the requested number of milliseconds.",
				parameters: Type.Object({ ms: Type.Number() }),
				async execute(_id: string, params: { ms: number }) {
					await new Promise((resolve) => setTimeout(resolve, params.ms));
					return { content: [{ type: "text", text: `waited ${params.ms}ms` }], details: { ms: params.ms } };
				},
			});
			pi.registerCommand("bg-verifier-reload", {
				description: "Verifier command that runs the same flow as /reload",
				handler: async (_args: string, ctx: ExtensionCommandContext) => {
					await ctx.reload();
				},
			});
		},
	};
}

export function loaderOptions(_box: Sandbox, ext: VerifierExtension) {
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

export function settings() {
	return SettingsManager.inMemory({
		compaction: { enabled: false },
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
	dispose: () => Promise<void>;
}

export async function startSession(tag: string, options: { box?: Sandbox; sessionManager?: SessionManager } = {}): Promise<Live> {
	const box = options.box ?? sandbox();
	const faux = newFaux(tag);
	const ext = verifierExtension(faux, tag);
	const settingsManager = settings();
	const resourceLoader = new DefaultResourceLoader({
		cwd: box.cwd,
		agentDir: box.agentDir,
		settingsManager,
		...loaderOptions(box, ext),
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
	// A real host (TUI, RPC, SDK embedder) binds extensions after creating the
	// session; this emits session_start to every extension instance.
	await session.bindExtensions({});
	const rec = record(session);
	return {
		session,
		faux,
		ext,
		rec,
		box,
		sessionManager,
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
	/** Bind extensions to the current runtime session (as a host does after every replacement) and record it. */
	rebind: () => Promise<Recorder>;
	dispose: () => Promise<void>;
}

/** Session-replacement runtime (the same machinery behind /new, /fork, /resume). */
export async function startRuntime(tag: string, box = sandbox()): Promise<LiveRuntime> {
	const faux = newFaux(tag);
	const ext = verifierExtension(faux, tag);
	const settingsManager = settings();
	const runtime = await createAgentSessionRuntime(
		async ({ cwd, sessionManager, sessionStartEvent }) => {
			const services = await createAgentSessionServices({
				cwd,
				agentDir: box.agentDir,
				settingsManager,
				resourceLoaderOptions: loaderOptions(box, ext),
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
		rebind,
		dispose: async () => {
			rec?.unsubscribe();
			// Not runtime.dispose(): that emits session_shutdown with reason "quit",
			// which in a real pi process only happens right before the process
			// exits. Several tests share this worker process, so a "quit" here would
			// legitimately let an implementation refuse further work. Tear the
			// session down without announcing a process-level quit.
			runtime.session.dispose();
		},
	};
}

export async function prompt(live: { session: AgentSession; faux: FauxProviderHandle }, steps: FauxResponseStep[], text = "go") {
	live.faux.setResponses(withAcks(steps));
	await live.session.prompt(text, { expandPromptTemplates: false, source: "interactive" });
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

export function pidAlive(pid: number): boolean {
	try {
		process.kill(pid, 0);
	} catch {
		return false;
	}
	// A zombie still answers kill(pid, 0) until its parent reaps it. Whether that
	// happens promptly depends on the container's PID 1, which is not the
	// implementation's doing, so a zombie counts as gone.
	try {
		const stat = readFileSync(`/proc/${pid}/stat`, "utf8");
		const state = stat.slice(stat.lastIndexOf(")") + 2, stat.lastIndexOf(")") + 3);
		if (state === "Z" || state === "X") return false;
	} catch {
		// /proc unavailable: fall back to the signal probe.
	}
	return true;
}

export async function readPid(file: string): Promise<number> {
	const text = await waitFor(() => (existsSync(file) ? readFileSync(file, "utf8").trim() : undefined), {
		label: `pidfile ${file}`,
	});
	return Number(text);
}

export function killGroupQuietly(pid: number) {
	for (const target of [-pid, pid]) {
		try {
			process.kill(target, "SIGKILL");
		} catch {
			// already gone
		}
	}
}

export function firstUserEntryId(sessionManager: SessionManager): string {
	for (const entry of sessionManager.getEntries()) {
		if (entry.type === "message" && entry.message.role === "user") return entry.id;
	}
	throw new Error("no user entry in session");
}

export function customEntriesInFile(path: string): number {
	return readFileSync(path, "utf8")
		.split("\n")
		.filter((line) => line.includes(`"customType":"${WAKE_TYPE}"`)).length;
}
