import { mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const clientDir = path.join(projectDir, 'dist', 'client');
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/').at(-1) ?? 'ai-infra-bench';
const basePath = process.env.GITHUB_PAGES_BASE_PATH ?? `/${repositoryName}`;
const normalizedBasePath = basePath.replace(/^\/+/, '');
const nestedDir = path.join(clientDir, normalizedBasePath);
const nestedAssetsDir = path.join(nestedDir, '_next');
const targetAssetsDir = path.join(clientDir, '_next');
const siteUrl = new URL(
  process.env.NEXT_PUBLIC_SITE_URL ?? 'https://ai-infra-bench.github.io',
);

let nestedEntries = [];
try {
  nestedEntries = await readdir(nestedAssetsDir);
} catch {
  // An empty base path already writes assets at the artifact root.
}

if (normalizedBasePath && nestedEntries.length > 0) {
  await rm(targetAssetsDir, { recursive: true, force: true });
  await mkdir(path.dirname(targetAssetsDir), { recursive: true });
  await rename(nestedAssetsDir, targetAssetsDir);
  await rm(nestedDir, { recursive: true, force: true });
}

const taskIndex = JSON.parse(
  await readFile(path.join(projectDir, 'app', 'generated', 'task-index.json'), 'utf8'),
);
const absoluteUrl = (route) => new URL(route, siteUrl).toString();
const sitemapUrls = [
  absoluteUrl('/'),
  ...taskIndex.map((task) => absoluteUrl(`/tasks/${task.slug}`)),
];
const sitemap = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...sitemapUrls.map((url) => `  <url><loc>${url}</loc></url>`),
  '</urlset>',
  '',
].join('\n');
const robots = [
  'User-Agent: *',
  'Allow: /',
  '',
  `Host: ${siteUrl.origin}`,
  `Sitemap: ${absoluteUrl('/sitemap.xml')}`,
  '',
].join('\n');

await Promise.all([
  writeFile(path.join(clientDir, 'robots.txt'), robots),
  writeFile(path.join(clientDir, 'sitemap.xml'), sitemap),
]);

console.log(`Prepared GitHub Pages artifact in ${clientDir}`);
