import { spawnSync } from "node:child_process";
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
			method: "POST", body: JSON.stringify({ role, group, event: name, pid: process.pid, resourceHints: Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("PI_TEAM_"))), ...fields }),
		});
	};

    // Test-only OS fault: arm one actual receiver endpoint, then shut its write
    // half immediately before the candidate attempts the finding write. No send
    // result is fabricated; the original write and candidate error handling run.
    let faultArmed = false;
    let faultChecking = false;
    if (process.env.PI_TEXT_ENDPOINT_FAULT === "1") {
        const timer = setInterval(async () => {
            if (role !== "ROOT" || faultArmed || faultChecking) return;
            faultChecking = true;
            try {
                const plan = await (await fetch(`${endpoint}/fault-plan`, {method:"POST",body:"{}"})).json() as any;
                if (!plan) return;
                const handles = (process as any)._getActiveHandles();
                let target: any;
                if (plan.mode === "rpc") {
                    target = handles.find((h:any) => h.constructor?.name === "ChildProcess" && h.pid === plan.pid)?.stdin;
                } else if (plan.mode === "tcp") {
                    target = handles.find((h:any) => h.constructor?.name === "Socket" && h.remotePort === plan.port);
                } else if (plan.mode === "unix") {
                    for (const h of handles) {
                        if (h.constructor?.name !== "Socket" || h.remotePort || !Number.isInteger(h._handle?.fd)) continue;
                        const probe = spawnSync("/usr/bin/python3", ["-I", "-c", "import socket,struct; s=socket.socket(fileno=3); print(struct.unpack('3i',s.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[0])"], {stdio:["ignore","pipe","pipe",h._handle.fd]});
                        if (Number(probe.stdout?.toString().trim()) === plan.pid) { target = h; break; }
                    }
                }
                if (!target || !Number.isInteger(target._handle?.fd)) throw new Error("selected receiver endpoint was not found");
                const original = target.write;
                const fd = target._handle.fd;
                target.write = function(...args: any[]) {
                    if (String(args[0]).includes(plan.marker)) {
                        target.write = original;
                        const fault = spawnSync("/usr/bin/python3", ["-I", "-c", "import socket; socket.socket(fileno=3).shutdown(socket.SHUT_WR)"], {stdio:["ignore","pipe","pipe",fd]});
                        if (fault.status !== 0) throw new Error(`OS fault failed: ${fault.stderr}`);
                        const record = spawnSync("/usr/bin/python3", ["-I", "-c", "import urllib.request,sys; urllib.request.urlopen(urllib.request.Request(sys.argv[1],data=sys.argv[2].encode(),method='POST'),timeout=5).read()", `${endpoint}/event`, JSON.stringify({role,group,event:"endpoint_fault_triggered",pid:process.pid,mode:plan.mode,receiverPid:plan.pid})], {stdio:["ignore","pipe","pipe"]});
                        if (record.status !== 0) throw new Error(`Fault observation failed: ${record.stderr}`);
                    }
                    return original.apply(this, args);
                };
                faultArmed = true;
                clearInterval(timer);
                await event("endpoint_fault_armed", {mode:plan.mode, receiverPid:plan.pid});
            } catch (error) {
                await event("endpoint_fault_error", {error:String(error)});
            } finally { faultChecking = false; }
        }, 25);
        timer.unref();
    }
	pi.registerProvider("text-test", {
		baseUrl: `${endpoint}/v1`, apiKey: "local-test-only", api: "openai-completions",
		headers: { "X-Pi-Test-Pid": String(process.pid) },
		models: [{
			id: "scripted", name: "Text behavior test", reasoning: false, input: ["text"],
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			contextWindow: 4194304, maxTokens: 2097152,
		}],
	});
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

}
