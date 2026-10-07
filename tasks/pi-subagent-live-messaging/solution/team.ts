import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface Member {
	id: string;
	agent: string;
	state: "pending" | "running" | "finished";
}

export interface Envelope {
	id: string;
	from: string;
	text: string;
	sequence: number;
}

export interface WorkerConfig {
	directory: string;
	id: string;
	extension: string;
}

export function inbox(directory: string, id: string): string {
	return path.join(directory, createHash("sha256").update(id).digest("hex"));
}

export async function locked<T>(directory: string, action: () => T): Promise<T> {
	const lock = path.join(directory, "lock");
	const deadline = Date.now() + 10000;
	while (true) {
		try {
			fs.mkdirSync(lock);
			break;
		} catch (error) {
			if ((error as NodeJS.ErrnoException).code !== "EEXIST" || Date.now() >= deadline) throw error;
			await new Promise<void>((resolve) => setTimeout(resolve, 5));
		}
	}
	try {
		return action();
	} finally {
		fs.rmdirSync(lock);
	}
}

export function readMembers(directory: string): Member[] {
	return JSON.parse(fs.readFileSync(path.join(directory, "members.json"), "utf8")) as Member[];
}

export function saveMembers(directory: string, members: Member[]): void {
	const target = path.join(directory, "members.json");
	const temporary = `${target}.${randomUUID()}`;
	fs.writeFileSync(temporary, JSON.stringify(members));
	fs.renameSync(temporary, target);
}

export function createTeam(tasks: { id?: string; agent: string }[]) {
	const ids = tasks.map((task) => task.id);
	if (ids.some((id) => typeof id !== "string" || id.length === 0) || new Set(ids).size !== ids.length) {
		throw new Error("Communication requires a distinct nonempty id for every parallel task");
	}
	const directory = fs.mkdtempSync(path.join(os.tmpdir(), "pi-team-"));
	const members: Member[] = tasks.map((task) => ({ id: task.id!, agent: task.agent, state: "pending" }));
	for (const member of members) fs.mkdirSync(inbox(directory, member.id));
	saveMembers(directory, members);
	const dispose = () => {
		process.off("exit", dispose);
		fs.rmSync(directory, { recursive: true, force: true });
	};
	// Print mode may exit immediately after its runtime has been cancelled.
	process.once("exit", dispose);
	return {
		async start(index: number): Promise<WorkerConfig> {
			return locked(directory, () => {
				const current = readMembers(directory);
				current[index].state = "running";
				saveMembers(directory, current);
				return {
					directory,
					id: current[index].id,
					extension: fileURLToPath(new URL("./team-worker.ts", import.meta.url)),
				};
			});
		},
		async finish(index: number): Promise<void> {
			await locked(directory, () => {
				const current = readMembers(directory);
				current[index].state = "finished";
				saveMembers(directory, current);
			});
		},
		dispose,
	};
}
