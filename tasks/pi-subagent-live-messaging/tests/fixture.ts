import { fauxProvider, fauxAssistantMessage, fauxToolCall, observeProviderRequest, observeFixtureReady } from "./trusted_faux.mjs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

// Test-only model endpoint and slow external-work boundary. This extension does
// not implement, read, poll, or inject teammate messages.
export default function fixture(pi: ExtensionAPI) {
	const endpoint = process.env.PI_TEXT_TEST_URL!;
	const task = process.argv.find((arg) => arg.startsWith("Task: ROLE:"));
	let role = task?.match(/ROLE:([A-Z]+)/)?.[1];
	let group = task?.match(/GROUP:([a-z]+)/)?.[1] ?? "one";
	const event = async (name: string, fields: Record<string, unknown> = {}) => {
		if (!role) return; // RPC workers receive their task after session startup.
		await fetch(`${endpoint}/event`, {
			method: "POST", body: JSON.stringify({ role, group, event: name, pid: process.pid, ...fields }),
		});
	};


    const faux = fauxProvider({
        provider: "text-test", api: "faux-pilot", tokenSize: { min: 1048576, max: 1048576 },
        models: [{ id: "scripted", contextWindow: 4194304, maxTokens: 2097152 }],
    });
    const nextResponse = async (context: any, options: any) => {
        const response = await fetch(`${endpoint}/faux`, {
            method: "POST", headers: { "X-Pi-Test-Pid": String(process.pid) },
            body: observeProviderRequest(context), signal: options?.signal,
        });
        if (!response.ok) throw new Error(await response.text());
        const delta = await response.json();
        // The coordinator decides only what the model says, never peer delivery.
        faux.appendResponses([nextResponse]);
        const content = delta.tool_calls
            ? delta.tool_calls.map((call: any) => fauxToolCall(
                call.function.name, JSON.parse(call.function.arguments), { id: call.id }))
            : delta.content ?? "";
        return fauxAssistantMessage(content, {
            stopReason: delta.tool_calls ? "toolUse" : "stop",
        });
    };
    faux.setResponses([nextResponse]);
    pi.registerProvider(faux.provider);

	// Bind unknown identities from the real prompt event, before any model/tool call.
	// This observes RPC input; it never supplies or changes the worker's context.
	pi.on("before_agent_start", async ({ prompt }) => {
		if (role) return;
		const identity = prompt.match(/\bROLE:([A-Z]+) GROUP:([a-z]+)/);
		role = identity?.[1] ?? "ROOT";
		group = identity?.[2] ?? "one";
		await event("identity_bound");
	});
	// Observation only: no message injection or resource cleanup on Pi's behalf.
	pi.on("before_provider_request", async () => {
		if (role !== "ROOT") return;
		const resources: Record<string, number> = {};
		for (const name of ["exit", "beforeExit", "SIGINT", "SIGTERM", "message", "disconnect"]) {
			resources[`listener:${name}`] = process.listenerCount(name);
		}
		const handles = (process as any)._getActiveHandles();
		for (const handle of handles) {
			if ([process.stdin, process.stdout, process.stderr].includes(handle)) continue;
			if (handle.remotePort === Number(new URL(endpoint).port)) continue;
			const kind = handle.constructor?.name;
			if (["Server", "Socket", "FSWatcher", "ChildProcess"].includes(kind)) {
				resources[`handle:${kind}`] = (resources[`handle:${kind}`] ?? 0) + 1;
			}
		}
		await event("resource_snapshot", {resources});
	});
	pi.on("session_start", async () => { await event("session_start"); });
    pi.on("tool_execution_end", async (result) => {
        await event("tool_execution_end", {toolCallId: result.toolCallId, toolName: result.toolName,
            result: result.result, isError: result.isError});
    });
	pi.on("session_shutdown", async () => { await event("session_shutdown"); });
	pi.on("message_end", async ({ message }) => {
		if (message.role === "toolResult" && message.isError) {
			await event("tool_error", { toolCallId: message.toolCallId });
		}
	});
	pi.registerTool({
		name: "test_work", label: "Controlled work", description: "Perform an ordinary external work step.",
		parameters: Type.Object({ stage: Type.String() }),
		async execute(_id, args, signal) {
			await event(`tool_start:${args.stage}`, {sockets: (process as any)._getActiveHandles().filter((h:any) => h.constructor?.name === "Socket" && h.remotePort && h.remotePort !== Number(new URL(endpoint).port)).map((h:any) => ({localPort:h.localPort,remotePort:h.remotePort}))});
			const response = await fetch(`${endpoint}/work`, {
				method: "POST", body: JSON.stringify({ role, group, stage: args.stage }), signal,
			});
			if (!response.ok) throw new Error(await response.text());
			const text = await response.text();
			if (process.env.PI_TEST_ORDINARY_STEERING === "1" && role === "B" && args.stage === "slow_work") {
				for (const content of ["Ordinary steering one: continue the investigation.", "Ordinary steering two: keep the answer concise."]) {
					pi.sendMessage({ customType: "ordinary-steering", content, display: false }, { deliverAs: "steer" });
				}
				await event("ordinary_steering_queued", { count: 2 });
			}
			await event(`tool_end:${args.stage}`);
			return { content: [{ type: "text", text }] };
		},
	});
	pi.registerTool({
		name: "test_probe", label: "Probe endpoint", description: "Call an API endpoint using its path.",
		parameters: Type.Object({ path: Type.String() }),
		async execute(_id, args) {
			const response = await fetch(`${endpoint}/probe`, {method: "POST", body: JSON.stringify({role, group, path: args.path})});
			return {content: [{type: "text", text: await response.text()}]};
		},
	});

    observeFixtureReady();

}
