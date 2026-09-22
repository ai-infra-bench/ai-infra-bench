#!/usr/bin/env node
/**
 * A separate pi OS process driven by the verifier. Uses the published package
 * entry points (dist) exactly like an external SDK consumer would. The
 * lifecycle suite copies this file into the workspace before spawning it so
 * package resolution uses the workspace node_modules.
 *
 * Modes:
 *   build   <sessionDir> <cwd> <agentDir> <out.json>   a prompt with a tool call, a manual compaction, a second prompt; exit
 *   resume  <sessionFile> <cwd> <agentDir> <out.json>  open the session file in a fresh process and run one prompt with a tool call; exit
 *   slow-tool <sessionFile> <cwd> <agentDir> <out.json> <marker>  resume, then a prompt whose tool writes <marker> and sleeps 20 s (the parent kills this process meanwhile)
 *   child-run <sessionDir> <cwd> <agentDir> <out.json>   a new session (a sub-agent spawned by a tool of another pi), one prompt with a tool call; exit
 */
import { writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { dirname, join } from "node:path";
import { fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall } from "@earendil-works/pi-ai/providers/faux";
import { createAgentSession, DefaultResourceLoader, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const [mode, target, cwd, agentDir, outFile, marker] = process.argv.slice(2);
const workspace = process.env.PI_WORKSPACE ?? "/workspace/pi";
const extensionPath = join(workspace, "packages/coding-agent/examples/extensions/agent-trace/index.ts");

const faux = fauxProvider({
	provider: "at-child",
	api: "at-child-api",
	models: [{ id: "at-child-model", contextWindow: 200_000, maxTokens: 8_192 }],
});
const toolCall = (name, args) => fauxAssistantMessage(fauxToolCall(name, args), { stopReason: "toolUse" });
const say = (text) => fauxAssistantMessage(fauxText(text));
const acks = Array.from({ length: 4 }, (_, i) => say(`ack ${i + 1}`));

const settingsManager = SettingsManager.inMemory({
	compaction: { enabled: true, keepRecentTokens: 1, reserveTokens: 16_384 },
	retry: { enabled: false },
});
const loader = new DefaultResourceLoader({
	cwd,
	agentDir,
	settingsManager,
	additionalExtensionPaths: [extensionPath],
	extensionFactories: [
		{
			name: "at-child-verifier",
			factory: (pi) => {
				pi.registerProvider(faux.provider);
				pi.registerTool({
					name: "echo",
					label: "Echo",
					description: "Returns its text argument.",
					parameters: Type.Object({ text: Type.String() }),
					async execute(_id, params) {
						if (marker && params.text === "slow") {
							writeFileSync(marker, JSON.stringify({ pid: process.pid, sessionFile: sessionManager.getSessionFile() }));
							await delay(20_000);
						}
						return { content: [{ type: "text", text: params.text }], details: {} };
					},
				});
			},
		},
	],
	noExtensions: true,
	noSkills: true,
	noPromptTemplates: true,
	noThemes: true,
	noContextFiles: true,
	systemPrompt: "Deterministic child session.",
});
await loader.reload();

const sessionManager = mode === "build" || mode === "child-run" || mode === "child-compact" ? SessionManager.create(cwd, target) : SessionManager.open(target, dirname(target));
const { session } = await createAgentSession({
	cwd,
	agentDir,
	model: faux.getModel(),
	thinkingLevel: "off",
	noTools: "builtin",
	resourceLoader: loader,
	sessionManager,
	settingsManager,
});
await session.bindExtensions({});

const prompt = async (steps, text = "go") => {
	faux.setResponses([...steps, ...acks]);
	await session.prompt(text, { expandPromptTemplates: false, source: "interactive" });
};
const compact = async () => {
	faux.setResponses([say("summary of the earlier window"), say("summary turn prefix")]);
	await session.compact();
};

const branch = () =>
	sessionManager.getBranch().map((entry) => ({
		id: entry.id,
		type: entry.type,
		role: entry.type === "message" ? entry.message.role : null,
		toolCallId: entry.type === "message" && entry.message.role === "toolResult" ? entry.message.toolCallId : null,
		tokensBefore: entry.type === "compaction" ? entry.tokensBefore : null,
	}));

if (mode === "build") {
	await prompt([toolCall("echo", { text: "built" }), say("done")], "build");
	await compact();
	await prompt([say("after compaction")], "continue");
} else if (mode === "resume") {
	await prompt([toolCall("echo", { text: "resumed" }), say("done again")], "resume");
} else if (mode === "slow-tool") {
	await prompt([toolCall("echo", { text: "slow" }), say("never reached")], "slow");
} else if (mode === "child-run" || mode === "child-compact") {
	await prompt([toolCall("echo", { text: "child work" }), say("child done")], "child task");
	if (mode === "child-compact") await compact();
} else {
	throw new Error(`unknown mode ${mode}`);
}
writeFileSync(
	outFile,
	JSON.stringify({
		sessionFile: session.sessionFile,
		sessionId: sessionManager.getSessionId(),
		sessionDir: sessionManager.getSessionDir(),
		pid: process.pid,
		branch: branch(),
	}),
);
session.dispose();
process.exit(0);
