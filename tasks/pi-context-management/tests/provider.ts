import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { installObservationHandlers } from "./context_observation.mjs";

// Only supplies model responses / external evidence and observes public events.
// No context, notes, history, or persistence behavior is implemented here.
export default function provider(pi: ExtensionAPI) {
	const endpoint = process.env.PI_CONTEXT_TEST_URL!;
	const contextWindow = Number(process.env.PI_CONTEXT_TEST_CONTEXT_WINDOW ?? 1000000);
	const maxTokens = Number(process.env.PI_CONTEXT_TEST_MAX_TOKENS ?? 4096);
	const largeContextWindow = Number(process.env.PI_CONTEXT_TEST_LARGE_CONTEXT_WINDOW ?? contextWindow);
	const largeMaxTokens = Number(process.env.PI_CONTEXT_TEST_LARGE_MAX_TOKENS ?? maxTokens);
	pi.registerProvider("context-test", {
		baseUrl: `${endpoint}/v1`, apiKey: "local-only", api: (process.env.PI_CONTEXT_TEST_API ?? "openai-completions") as "openai-completions" | "openai-responses",
		models: [{ id: "scripted", name: "Scripted behavior", reasoning: process.env.PI_CONTEXT_TEST_REASONING === "1", input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			contextWindow, maxTokens, compat: { supportsStrictMode: true } },
			{ id: "scripted-large", name: "Scripted large-context behavior", reasoning: process.env.PI_CONTEXT_TEST_REASONING === "1", input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			contextWindow: largeContextWindow, maxTokens: largeMaxTokens, compat: { supportsStrictMode: true } }],
	});
	pi.registerTool({
		name: "evidence", label: "Evidence", description: "Read external diagnostic evidence." + "T".repeat(Number(process.env.PI_CONTEXT_TEST_TOOL_PADDING ?? 0)),
		parameters: Type.Object({ key: Type.String(), request_label: Type.Optional(Type.String()) }),
		async execute(_id, args, signal) {
			const response = await fetch(`${endpoint}/evidence`, { method: "POST", body: JSON.stringify(args), signal });
			return { content: [{ type: "text", text: await response.text() }], details: {} };
		},
	});
	// Optional HTTP diagnostics remain deliberately outside the scoring channel.
	pi.on("context", async (e) => {
		await fetch(`${endpoint}/event`, { method: "POST", body: JSON.stringify({ type: "context_observation",
			reminders: e.messages.filter((m) => m.role === "custom" && m.customType === "context_capacity_reminder")
				.map((m) => typeof m.content === "string" ? m.content : m.content.filter((p: any) => p.type === "text").map((p: any) => p.text).join("")) }) });
	});
	installObservationHandlers(pi);
}
