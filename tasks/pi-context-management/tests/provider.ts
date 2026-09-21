import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// Only supplies model responses / external evidence and observes public events.
// No context, notes, history, or persistence behavior is implemented here.
export default function provider(pi: ExtensionAPI) {
	const endpoint = process.env.PI_CONTEXT_TEST_URL!;
	const event = async (data: unknown) => {
		await fetch(`${endpoint}/event`, { method: "POST", body: JSON.stringify(data) });
	};
	pi.registerProvider("context-test", {
		baseUrl: `${endpoint}/v1`, apiKey: "local-only", api: (process.env.PI_CONTEXT_TEST_API ?? "openai-completions") as "openai-completions" | "openai-responses",
		models: [{ id: "scripted", name: "Scripted behavior", reasoning: false, input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, contextWindow: 1000000, maxTokens: 4096, compat: { supportsStrictMode: true } }],
	});
	pi.on("session_start", async (_e, ctx) => {
		await event({ type: "session", id: ctx.sessionManager.getSessionId(), file: ctx.sessionManager.getSessionFile() });
	});
	pi.on("tool_execution_end", async (e) => { await event(e); });
	pi.on("before_provider_request", async (_e, ctx) => {
		await event({ type: "request_session", id: ctx.sessionManager.getSessionId() });
	});
	pi.registerTool({
		name: "evidence", label: "Evidence", description: "Read external diagnostic evidence.",
		parameters: Type.Object({ key: Type.String() }),
		async execute(_id, args, signal) {
			const response = await fetch(`${endpoint}/evidence`, { method: "POST", body: JSON.stringify(args), signal });
			return { content: [{ type: "text", text: await response.text() }], details: {} };
		},
	});
}
