import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { makeBox, WORKSPACE } from "./plan_support.mjs";

const boxes: ReturnType<typeof makeBox>[] = [];
const verifier = join(WORKSPACE, "packages/coding-agent/test/__plan_verifier__");
const child = join(verifier, "fixtures/plan_child.mjs");
function box() { const value = makeBox(); boxes.push(value); return value; }
afterEach(() => { for (const value of boxes.splice(0)) rmSync(value.root, { recursive: true, force: true }); });
function run(config: Record<string, unknown>) {
  const root = (config.box as { root: string }).root;
  const nonce = randomUUID(); const input = join(root, `${nonce}.input.json`); const outFile = join(root, `${nonce}.result.json`);
  writeFileSync(input, JSON.stringify({ ...config, outFile }));
  const result = spawnSync(process.execPath, [child, input], { cwd: WORKSPACE, env: { ...process.env, PI_WORKSPACE: WORKSPACE, PI_OFFLINE: "1", PI_TELEMETRY: "0" }, timeout: 30000, encoding: "utf8", maxBuffer: 2000000 });
  expect(result.error, result.stderr).toBeUndefined(); expect(result.status, result.stderr).toBe(0);
  expect(existsSync(outFile), "child exit 0 without its observed state is not success").toBe(true);
  const report = JSON.parse(readFileSync(outFile, "utf8")); expect(report.errors).toEqual([]);
  expect(report.pid).not.toBe(process.pid); return report;
}
describe("plan lifecycle", () => {
  it("L01 planning resumes in a new process with identity revision strings and exact original tools", () => {
    const value = box(); const seeded = run({ box: value, mode: "seed-planning" });
    expect(seeded.state.mode).toBe("planning"); expect(existsSync(seeded.sessionFile)).toBe(true);
    const resumed = run({ box: value, mode: "resume-and-approve", sessionFile: seeded.sessionFile, flag: true });
    expect(resumed.pid).not.toBe(seeded.pid); expect(resumed.state).toEqual(seeded.state);
    expect([...resumed.tools].sort()).toEqual(["grep", "plan_submit"]);
    expect(resumed.callsAtOpen).toBe(0); expect(resumed.calls).toBe(0); expect(resumed.approval.ok).toBe(true);
    expect(resumed.afterState).toEqual({ ...seeded.state, mode: "approved", approvedRevision: seeded.state.revision });
    expect([...resumed.afterTools].sort()).toEqual(["grep", "verifier_effect", "write"]); expect(resumed.executions).toBe("once\n");
  });
  it("L02 approved resume ignores plan flag and never replays execution", () => {
    const value = box(); const seeded = run({ box: value, mode: "seed-approved" }); expect(seeded.executions).toBe("once\n");
    expect(seeded.state.mode).toBe("approved"); expect(seeded.approvedCount).toBe(1);
    const resumed = run({ box: value, mode: "resume", sessionFile: seeded.sessionFile, flag: true });
    expect(resumed.pid).not.toBe(seeded.pid); expect(resumed.state).toEqual(seeded.state);
    expect([...resumed.tools].sort()).toEqual(["grep", "verifier_effect", "write"]);
    expect(resumed.callsAtOpen).toBe(0); expect(resumed.calls).toBe(0); expect(resumed.executions).toBe("once\n"); expect(resumed.approvedCount).toBe(1);
  });
  it("L03 fresh sessions isolate foreign state and plan flag starts only a fresh cycle", () => {
    const value = box(); const seeded = run({ box: value, mode: "seed-approved" });
    const fresh = run({ box: value, mode: "fresh", seedEntries: seeded.entries.filter((entry: { type: string }) => entry.type === "custom") });
    expect(fresh.state.sessionId).not.toBe(seeded.state.sessionId);
    expect(fresh.state).toEqual({ sessionId: fresh.state.sessionId, mode: "normal", planId: null, revision: 0, steps: [], approvedRevision: null });
    expect(fresh.calls).toBe(0); expect(fresh.approvedCount).toBe(0);
    const flagged = run({ box: value, mode: "fresh", flag: true });
    expect(flagged.state.mode).toBe("planning"); expect(flagged.state.revision).toBe(0); expect(flagged.state.steps).toEqual([]); expect(flagged.state.approvedRevision).toBeNull();
    expect(flagged.state.planId).not.toBe(seeded.state.planId); expect(flagged.tools).not.toContain("write"); expect(flagged.calls).toBe(0);
  });
  it("L04 a persisted normal session ignores plan flag on cross process resume", () => {
    const value = box(); const seeded = run({ box: value, mode: "seed-normal" });
    expect(seeded.state.mode).toBe("normal"); expect(existsSync(seeded.sessionFile)).toBe(true);
    const resumed = run({ box: value, mode: "resume", sessionFile: seeded.sessionFile, flag: true });
    expect(resumed.pid).not.toBe(seeded.pid); expect(resumed.state).toEqual(seeded.state);
    expect(resumed.tools).not.toContain("plan_submit"); expect(resumed.tools).toContain("write");
    expect(resumed.callsAtOpen).toBe(0); expect(resumed.calls).toBe(0); expect(resumed.approvedCount).toBe(0);
  });
});
