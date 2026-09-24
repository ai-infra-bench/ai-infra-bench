import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// Verifier-owned user extension, installed through settings.json like the candidate's.
// Every pi process of a case loads it: the parent and every fork. It registers the
// scripted model endpoint, a slow tool, and a reload command, and reports lifecycle
// observations to the verifier. It never reads or changes the fork machinery.
export default function fixture(pi: ExtensionAPI) {
	const endpoint = process.env.PI_FORK_TEST_URL!;
	const post = async (path: string, body: Record<string, unknown>) => {
		const response = await fetch(`${endpoint}${path}`, {
			method: "POST",
			headers: { "content-type": "application/json" },
			body: JSON.stringify({ pid: process.pid, ...body }),
		});
		return response.text();
	};
	const event = (name: string, fields: Record<string, unknown> = {}) => post("/event", { event: name, ...fields });

	const model = (id: string) => ({
		id,
		name: `Fork test ${id}`,
		reasoning: true,
		input: ["text" as const],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 1_000_000,
		maxTokens: 64_000,
		compat: { supportsReasoningEffort: true },
	});
	pi.registerProvider("fork-test", {
		baseUrl: `${endpoint}/v1`,
		apiKey: "local-test-only",
		api: "openai-completions",
		headers: { "X-Pi-Test-Pid": String(process.pid) },
		models: [model("scripted-a"), model("scripted-b")],
	});

	// A tool that stays busy until the verifier releases it, so a case can hold the
	// parent inside a running tool while a fork finishes.
	pi.registerTool({
		name: "hold",
		label: "Hold",
		description: "Waits until the test releases it.",
		parameters: Type.Object({ key: Type.String() }),
		async execute(toolCallId, params) {
			await event("hold_start", { key: params.key, toolCallId });
			const released = await post("/hold", { key: params.key });
			await event("hold_end", { key: params.key, toolCallId });
			return { content: [{ type: "text", text: `held ${params.key}: ${released}` }], details: {} };
		},
	});

	pi.registerCommand("verifier-reload", {
		description: "Reload extensions (verifier)",
		handler: async (_args, ctx) => {
			await event("reload_requested");
			await ctx.reload();
		},
	});

	pi.on("session_start", async (evt, ctx) => {
		await event("session_start", { reason: evt.reason, sessionFile: ctx.sessionManager.getSessionFile() ?? null });
	});
	pi.on("session_shutdown", async (evt, ctx) => {
		await event("session_shutdown", { reason: evt.reason, sessionFile: ctx.sessionManager.getSessionFile() ?? null });
	});
	pi.on("agent_start", async (_evt, ctx) => {
		await event("agent_start", { sessionFile: ctx.sessionManager.getSessionFile() ?? null });
	});
	pi.on("agent_end", async (_evt, ctx) => {
		await event("agent_end", { sessionFile: ctx.sessionManager.getSessionFile() ?? null });
	});
	// Test-only process fault: after a model response the verifier can ask this process
	// to exit abnormally (the "fork process crashes" case). No result is fabricated.
	pi.on("turn_end", async () => {
		if ((await event("turn_end")) === "exit") process.exit(3);
	});
	pi.on("tool_execution_end", async (evt) => {
		await event("tool_execution_end", { toolName: evt.toolName, toolCallId: evt.toolCallId, isError: evt.isError });
	});
}
