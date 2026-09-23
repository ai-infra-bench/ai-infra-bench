import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as path from "node:path";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { type Envelope, inbox, locked, readMembers, saveMembers } from "./team.ts";

export default function teamWorker(pi: ExtensionAPI) {
	const directory = process.env.PI_TEAM_DIRECTORY;
	const self = process.env.PI_TEAM_MEMBER;
	if (!directory || !self) throw new Error("Team membership is not configured");
	let sequence = 0;
	const pendingContext = new Map<string, Extract<AgentMessage, { role: "custom" }>>();
	pi.on("context", (event) => {
		// Steering may be behind unrelated queued input. Include accepted findings
		// immediately, until their persistent message reaches normal history.
		for (const message of event.messages) {
			if (message.role !== "custom" || message.customType !== "team_findings") continue;
			const details = message.details as { batchId?: string } | undefined;
			if (details?.batchId) pendingContext.delete(details.batchId);
		}
		if (pendingContext.size) return { messages: [...event.messages, ...pendingContext.values()] };
	});
	pi.registerTool({
		name: "team_members",
		label: "Team members",
		description: "Discover the instances in this parallel dispatch.",
		parameters: Type.Object({}),
		async execute() {
			const result = await locked(directory, () => ({ self, members: readMembers(directory) }));
			return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
		},
	});
	pi.registerTool({
		name: "team_send",
		label: "Share a finding",
		description: "Send a finding to an instance ID or broadcast to current live teammates.",
		parameters: Type.Object({
			to: Type.Optional(Type.String()),
			broadcast: Type.Optional(Type.Boolean()),
			message: Type.String(),
		}),
		async execute(_call, args) {
			if (!args.message || Buffer.byteLength(args.message, "utf8") > 1024 * 1024) {
				throw new Error("message must be nonempty and no larger than 1 MiB");
			}
			if ((args.broadcast === true) === (typeof args.to === "string" && args.to.length > 0)) {
				throw new Error("Specify exactly one recipient or broadcast: true");
			}
			const result = await locked(directory, () => {
				const members = readMembers(directory);
				const targets = args.broadcast
					? members.filter((member) => member.state === "running" && member.id !== self).map((member) => member.id)
					: [args.to!];
				const accepted: string[] = [];
				const failed: { id: string; reason: string }[] = [];
				const envelope: Envelope = { id: randomUUID(), from: self, text: args.message, sequence: ++sequence };
				for (const id of targets) {
					const member = members.find((entry) => entry.id === id);
					if (!member || member.state !== "running" || id === self) {
						failed.push({ id, reason: id === self ? "self recipient" : (member?.state ?? "unknown recipient") });
						continue;
					}
					try {
						fs.writeFileSync(path.join(inbox(directory, id), `${envelope.id}.json`), JSON.stringify(envelope));
						accepted.push(id);
					} catch (error) {
						failed.push({ id, reason: String(error) });
					}
				}
				return { accepted, failed };
			});
			return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };
		},
	});
	pi.on("turn_end", async (event, ctx) => {
		const messages = await locked(directory, () => {
			const mailbox = inbox(directory, self);
			const files = fs.readdirSync(mailbox).filter((file) => file.endsWith(".json"));
			const queued = files.map((file) => JSON.parse(fs.readFileSync(path.join(mailbox, file), "utf8")) as Envelope);
			queued.sort((a, b) => a.from.localeCompare(b.from) || a.sequence - b.sequence);
			for (const file of files) fs.unlinkSync(path.join(mailbox, file));
			const terminal = event.message.role === "assistant" && event.message.stopReason !== "toolUse";
			if (queued.length === 0 && terminal && !ctx.hasPendingMessages()) {
				const members = readMembers(directory);
				const member = members.find((entry) => entry.id === self);
				if (member) member.state = "finished";
				saveMembers(directory, members);
			}
			return queued;
		});
		if (messages.length > 0) {
			const batchId = randomUUID();
			const message: Extract<AgentMessage, { role: "custom" }> = {
				role: "custom",
				customType: "team_findings",
				content: messages.map((message) => `Message from ${message.from}:\n${message.text}`).join("\n\n"),
				display: true,
				details: { messages, batchId },
				timestamp: Date.now(),
			};
			pendingContext.set(batchId, message);
			pi.sendMessage(message, { deliverAs: "steer", triggerTurn: true });
		}
	});
}
