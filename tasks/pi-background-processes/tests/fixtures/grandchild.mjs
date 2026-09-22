#!/usr/bin/env node
// Grandchild that ignores SIGTERM. Only SIGKILL (or process-group kill) ends it.
import { writeFileSync } from "node:fs";

const pidfile = process.argv[2];
if (pidfile) writeFileSync(pidfile, String(process.pid));
process.on("SIGTERM", () => {});
process.on("SIGINT", () => {});
setInterval(() => {}, 1 << 30);
