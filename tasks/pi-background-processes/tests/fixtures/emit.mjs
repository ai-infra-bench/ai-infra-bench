#!/usr/bin/env node
// Deterministic background-process fixture used by the verifier.
// Emits scripted stdout lines on a timeline, optionally spawns a SIGTERM-ignoring
// grandchild, optionally floods stdout, then exits with the requested code.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && i + 1 < args.length ? args[i + 1] : fallback;
};
const has = (name) => args.includes(`--${name}`);

const readyAfter = Number(opt("ready-after", "-1"));
const readyLine = opt("ready-line", "READY server listening on 8080");
const errorAfter = Number(opt("error-after", "-1"));
const errorCount = Number(opt("error-count", "1"));
const errorLine = opt("error-line", "ERR build failed");
const exitAfter = Number(opt("exit-after", "-1"));
const exitCode = Number(opt("exit-code", "0"));
const floodMb = Number(opt("flood-mb", "0"));
const pidfile = opt("pidfile", null);
const grandchildPidfile = opt("spawn-grandchild", null);
const ignoreTerm = has("ignore-sigterm");

if (pidfile) writeFileSync(pidfile, String(process.pid));
if (ignoreTerm) process.on("SIGTERM", () => {});

let grandchild;
if (grandchildPidfile) {
  const here = dirname(fileURLToPath(import.meta.url));
  grandchild = spawn(process.execPath, [join(here, "grandchild.mjs"), grandchildPidfile], {
    stdio: "ignore",
  });
}

const out = (line) => process.stdout.write(`${line}\n`);
out("line 1 started");
out("line 2 warming up");

if (floodMb > 0) {
  // ~100 bytes per line; write synchronously in chunks so the byte count is exact.
  const target = floodMb * 1024 * 1024;
  let written = 0;
  let n = 3;
  const chunk = [];
  while (written < target) {
    const line = `line ${n} ${"x".repeat(90 - String(n).length)}`;
    chunk.push(line);
    written += line.length + 1;
    n += 1;
    if (chunk.length >= 2000) {
      process.stdout.write(chunk.join("\n") + "\n");
      chunk.length = 0;
    }
  }
  if (chunk.length) process.stdout.write(chunk.join("\n") + "\n");
  out(`line ${n} flood done`);
}

if (readyAfter >= 0) setTimeout(() => out(readyLine), readyAfter);
if (errorAfter >= 0) {
  setTimeout(() => {
    for (let i = 1; i <= errorCount; i += 1) out(`${errorLine} ${i}`);
  }, errorAfter);
}
if (exitAfter >= 0) {
  setTimeout(() => {
    out("line final exiting");
    process.stdout.write("", () => process.exit(exitCode));
  }, exitAfter);
} else {
  setInterval(() => {}, 1 << 30);
}
