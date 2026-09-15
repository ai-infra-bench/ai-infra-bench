import { mkdirSync, statfsSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { getFileRevision } from "/workspace/pi/packages/coding-agent/dist/utils/paths.js";
const roots = [{ name: "overlay", path: "/tmp/authdiag-overlay" }, { name: "tmpfs", path: "/dev/shm/authdiag-tmpfs" }];
const oldContent = JSON.stringify({ anthropic: { type: "api_key", key: "old" } });
const newContent = JSON.stringify({ anthropic: { type: "api_key", key: "new" } });
if (oldContent.length !== newContent.length) throw new Error("Probe requires equal-length contents");
console.log(JSON.stringify({ kind: "design", uid: process.getuid(), gid: process.getgid(), node: process.version, rounds: 5, samplesPerRound: 200, bytes: Buffer.byteLength(oldContent), revisionFunction: "Base getFileRevision from dist/utils/paths.js", date: new Date().toISOString() }));
for (let round = 1; round <= 5; round++) {
  for (const root of round % 2 ? roots : [...roots].reverse()) {
    mkdirSync(root.path, { recursive: true });
    const file = join(root.path, `revision-round-${round}.json`);
    const fsType = statfsSync(root.path).type.toString(16);
    let collisions = 0;
    for (let sample = 1; sample <= 200; sample++) {
      writeFileSync(file, oldContent);
      const before = getFileRevision(file);
      const start = process.hrtime.bigint();
      writeFileSync(file, newContent);
      const after = getFileRevision(file);
      const elapsedNs = (process.hrtime.bigint() - start).toString();
      if (before === undefined || after === undefined) throw new Error("Missing revision");
      const previous = before.split(":"), next = after.split(":");
      const collision = before === after;
      if (collision) collisions++;
      console.log(JSON.stringify({ kind: "sample", filesystem: root.name, fsType, round, sample, before, after, collision, mtimeDeltaNs: (BigInt(next[3]) - BigInt(previous[3])).toString(), ctimeDeltaNs: (BigInt(next[4]) - BigInt(previous[4])).toString(), elapsedNs }));
    }
    console.log(JSON.stringify({ kind: "round", filesystem: root.name, fsType, round, samples: 200, collisions }));
  }
}
