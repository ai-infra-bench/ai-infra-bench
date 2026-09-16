/* Trusted Node preload: the root Vitest coordinator writes reports; only its
 * actual Vitest 4 fork worker drops privileges before loading any test code. */
const entry = process.argv[1] || "";
if (entry === "/workspace/pi/node_modules/vitest/dist/workers/forks.js") {
  if (typeof process.getuid !== "function") throw new Error("Verifier requires POSIX privilege separation");
  if (process.getuid() === 0) {
    process.setgroups([]);
    process.setgid(65534);
    process.setuid(65534);
  }
  if (process.getuid() !== 65534 || process.getgid() !== 65534) throw new Error("Verifier worker privilege drop failed");
  process.env.HOME = require("node:fs").mkdtempSync("/tmp/pi-verifier-home-");
  process.env.JITI_FS_CACHE = "false";
  process.stderr.write(`VERIFIER_WORKER_UID=${process.getuid()} ENTRY=${entry}\n`);
}
