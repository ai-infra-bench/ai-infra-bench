import { mkdir, readdir, rename, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const clientDir = path.join(projectDir, 'dist', 'client');
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/').at(-1) ?? 'ai-infra-bench';
const basePath = process.env.GITHUB_PAGES_BASE_PATH ?? `/${repositoryName}`;
const nestedDir = path.join(clientDir, basePath.replace(/^\/+/, ''));
const nestedAssetsDir = path.join(nestedDir, '_next');
const targetAssetsDir = path.join(clientDir, '_next');

let nestedEntries = [];
try {
  nestedEntries = await readdir(nestedAssetsDir);
} catch {
  // An empty base path already writes assets at the artifact root.
}

if (nestedEntries.length > 0) {
  await rm(targetAssetsDir, { recursive: true, force: true });
  await mkdir(path.dirname(targetAssetsDir), { recursive: true });
  await rename(nestedAssetsDir, targetAssetsDir);
  await rm(nestedDir, { recursive: true, force: true });
}

console.log(`Prepared GitHub Pages artifact in ${clientDir}`);
