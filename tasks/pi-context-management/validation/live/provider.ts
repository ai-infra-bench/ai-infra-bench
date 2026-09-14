import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

export default function liveProvider(pi: ExtensionAPI) {
	const observer = process.env.PI_LIVE_OBSERVER!;
	const model = process.env.PI_LIVE_MODEL!;
	const post = async (path: string, value: unknown) => {
		const response = await fetch(observer + path, { method: "POST", body: JSON.stringify(value) });
		const body = await response.text();
		if (!response.ok) throw new Error(body);
		return body;
	};
	pi.registerProvider("live-eval", {
		baseUrl: process.env.PI_LIVE_GATEWAY!, apiKey: "router-local", api: "openai-responses",
		models: [{ id: model, name: model, reasoning: true, input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 128000, maxTokens: 8192, compat: { supportsStrictMode: true } }],
	});
	pi.on("session_start", async (_e, ctx) => {
		await post("/event", { type: "session", id: ctx.sessionManager.getSessionId() });
	});
	pi.on("before_provider_request", async (e, ctx) => {
		await post("/event", { type: "request", session_id: ctx.sessionManager.getSessionId(), payload: e.payload });
	});
	pi.on("tool_execution_end", async (e) => { await post("/event", e); });
	pi.on("message_end", async (e) => {
		if (e.message.role === "assistant") await post("/event", { type: "assistant", message: e.message });
	});
	pi.registerTool({
		name: "inspect_run", label: "Inspect experiment", description: "Read the retained diagnostic snapshot for run A, B, or C. Each snapshot is readable once; subsequent recovery must use your session history.",
		parameters: Type.Object({ run_id: Type.Union([Type.Literal("A"), Type.Literal("B"), Type.Literal("C")]) }),
		async execute(_id, args) {
			return { content: [{ type: "text", text: await post("/run", args) }], details: {} };
		},
	});
	pi.registerTool({
		name: "submit_report", label: "Submit investigation", description: "Record the requested audit report after the user asks for the second-stage evidence check. Returns a receipt, not grading feedback.",
		parameters: Type.Object({
			chosen_run: Type.String(), p95_ms: Type.Number(), audit_receipt: Type.String(), checksum: Type.String(),
			boundary_sample_id: Type.String(), explanation: Type.String(),
			history_refs: Type.Array(Type.Object({ window_id: Type.String(), item_id: Type.String() }), { minItems: 1 }),
		}),
		async execute(_id, args) {
			return { content: [{ type: "text", text: await post("/report", args) }], details: {} };
		},
	});
}
