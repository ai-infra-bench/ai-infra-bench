// Author-side compatibility observation; never copied into the agent image.
// Usage: node --experimental-strip-types check_public_rewind.mjs /path/to/core.ts
import { createHash } from 'node:crypto';
import { chmod, mkdtemp, readFile, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const source = process.argv[2];
if (!source) throw new Error('Supply the public pi-rewind core.ts snapshot');
const bytes = await readFile(source);
const core = await import(pathToFileURL(source));
const root = await mkdtemp(join(tmpdir(), 'public-rewind-check-'));
function git(...args) { return execFileSync('git', args, { cwd: root, encoding: 'utf8' }); }
git('init', '-q');
git('config', 'user.name', 'Fixture');
git('config', 'user.email', 'fixture@example.invalid');
git('config', 'core.filemode', 'true');
await writeFile(join(root, 'tracked.txt'), 'checkpoint bytes');
await chmod(join(root, 'tracked.txt'), 0o640);
git('add', '.'); git('commit', '-qm', 'fixture');
const cp = await core.createCheckpoint({ root, id: 'compatibility-observation', sessionId: 'fixture-session', trigger: 'turn', turnIndex: 0 });
await writeFile(join(root, 'tracked.txt'), 'request bytes');
await chmod(join(root, 'tracked.txt'), 0o600);
await writeFile(join(root, 'tracked.txt'), 'human edit after request');
await writeFile(join(root, 'unrelated-human.txt'), 'human-owned unrelated content');
let rejected = false;
try { await core.restoreCheckpoint(root, cp); } catch { rejected = true; }
let unrelated;
try { unrelated = await readFile(join(root, 'unrelated-human.txt'), 'utf8'); } catch { unrelated = null; }
console.log(JSON.stringify({
  source_sha256: createHash('sha256').update(bytes).digest('hex'),
  tested_surface: 'public createCheckpoint and restoreCheckpoint functions, disposable Git fixture',
  rejected_human_conflict: rejected,
  protected_human_content: (await readFile(join(root, 'tracked.txt'), 'utf8')) === 'human edit after request',
  preserved_unrelated_human_file: unrelated === 'human-owned unrelated content',
  checkpoint_mode: '0640', observed_mode: (await stat(join(root, 'tracked.txt'))).mode.toString(8).slice(-4),
  note: 'A direct public-core observation, not a full Pi adapter or a Harbor score.'
}, null, 2));
