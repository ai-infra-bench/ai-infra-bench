import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import rehypeShikiFromHighlighter from '@shikijs/rehype/core';
import rehypeStringify from 'rehype-stringify';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { createHighlighter } from 'shiki';
import { unified } from 'unified';

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tasksDir = path.resolve(projectDir, '..', 'tasks');
const outputDir = path.join(projectDir, 'app', 'generated');
const outputFile = path.join(outputDir, 'tasks.json');

const highlighter = await createHighlighter({
  themes: ['vitesse-light'],
  langs: ['bash', 'c', 'diff', 'json', 'python', 'text'],
});

function languageForFile(name) {
  if (name.endsWith('.sh')) return 'bash';
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.c')) return 'c';
  if (name.endsWith('.patch') || name.endsWith('.diff')) return 'diff';
  return 'text';
}

function highlightCode(content, language) {
  return highlighter.codeToHtml(content, {
    lang: language,
    theme: 'vitesse-light',
    transformers: [{
      pre(node) {
        delete node.properties.tabindex;
      },
    }],
  });
}

async function renderInstruction(markdown) {
  const file = await unified()
    .use(remarkParse)
    .use(remarkGfm)
    .use(remarkRehype)
    .use(rehypeShikiFromHighlighter, highlighter, {
      theme: 'vitesse-light',
      defaultLanguage: 'text',
      fallbackLanguage: 'text',
      transformers: [{
        pre(node) {
          delete node.properties.tabindex;
        },
      }],
    })
    .use(rehypeStringify)
    .process(markdown);

  return String(file);
}

function prioritizeFiles(files, preferredNames) {
  return files.sort((a, b) => {
    const aRank = preferredNames.indexOf(a.name);
    const bRank = preferredNames.indexOf(b.name);
    if (aRank !== -1 || bRank !== -1) {
      if (aRank === -1) return 1;
      if (bRank === -1) return -1;
      return aRank - bRank;
    }
    return a.name.localeCompare(b.name);
  });
}

async function readTextFiles(directory, prefix = '') {
  let entries;
  try {
    entries = await readdir(directory, { withFileTypes: true });
  } catch {
    return [];
  }

  const files = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    const relativePath = path.join(prefix, entry.name);
    if (entry.isDirectory()) {
      files.push(...await readTextFiles(absolutePath, relativePath));
      continue;
    }

    try {
      files.push({
        name: relativePath,
        content: (await readFile(absolutePath, 'utf8')).trimEnd(),
      });
    } catch {
      continue;
    }
  }

  return files.sort((a, b) => a.name.localeCompare(b.name));
}

function getSection(source, name) {
  const lines = source.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `[${name}]`);
  if (start === -1) return '';
  const next = lines.findIndex((line, index) => index > start && /^\s*\[.+\]\s*$/.test(line));
  return lines.slice(start + 1, next === -1 ? lines.length : next).join('\n');
}

function getValue(source, key) {
  const match = source.match(new RegExp(`^${key}\\s*=\\s*(.+)$`, 'm'));
  if (!match) return null;
  const raw = match[1].trim();

  if (raw.startsWith('[') || raw.startsWith('"')) {
    try {
      return JSON.parse(raw);
    } catch {
      return raw.replace(/^"|"$/g, '');
    }
  }

  if (/^-?\d+$/.test(raw)) return Number(raw);
  if (raw === 'true' || raw === 'false') return raw === 'true';
  return raw;
}

const entries = await readdir(tasksDir, { withFileTypes: true });
const tasks = [];

for (const entry of entries) {
  if (!entry.isDirectory()) continue;

  const taskDir = path.join(tasksDir, entry.name);
  let manifest;
  let instruction;

  try {
    [manifest, instruction] = await Promise.all([
      readFile(path.join(taskDir, 'task.toml'), 'utf8'),
      readFile(path.join(taskDir, 'instruction.md'), 'utf8'),
    ]);
  } catch {
    continue;
  }

  const task = getSection(manifest, 'task');
  const metadata = getSection(manifest, 'metadata');
  const agent = getSection(manifest, 'agent');
  const environment = getSection(manifest, 'environment');
  const verifier = getSection(manifest, 'verifier');
  const verifierFiles = prioritizeFiles(
    await readTextFiles(path.join(taskDir, 'tests')),
    ['test.sh'],
  );
  const solutionFiles = prioritizeFiles(
    await readTextFiles(path.join(taskDir, 'solution')),
    ['solve.sh', 'oracle.patch'],
  );

  tasks.push({
    slug: entry.name,
    name: getValue(task, 'name') ?? entry.name,
    version: getValue(task, 'version'),
    description: getValue(task, 'description') ?? '',
    keywords: getValue(task, 'keywords') ?? [],
    track: getValue(metadata, 'track'),
    workloadType: getValue(metadata, 'workload_type'),
    subsystems: getValue(metadata, 'subsystems') ?? [],
    repository: getValue(metadata, 'repository'),
    baseCommit: getValue(metadata, 'base_commit'),
    dependencyCutoff: getValue(metadata, 'dependency_cutoff'),
    publicationState: getValue(metadata, 'publication_state'),
    agentTimeoutSec: getValue(agent, 'timeout_sec'),
    accelerator: getValue(environment, 'accelerator'),
    cpus: getValue(environment, 'cpus'),
    memoryMb: getValue(environment, 'memory_mb'),
    networkMode: getValue(environment, 'network_mode'),
    verifierTimeoutSec: getValue(verifier, 'timeout_sec'),
    instructionHtml: await renderInstruction(instruction.trim()),
    verifierFiles: verifierFiles.map((file) => ({
      name: file.name,
      highlightedHtml: highlightCode(file.content, languageForFile(file.name)),
      lineCount: file.content ? file.content.split(/\r?\n/).length : 0,
    })),
    solutionFiles: solutionFiles.map((file) => ({
      name: file.name,
      highlightedHtml: highlightCode(file.content, languageForFile(file.name)),
      lineCount: file.content ? file.content.split(/\r?\n/).length : 0,
    })),
  });
}

tasks.sort((a, b) => a.slug.localeCompare(b.slug));

await mkdir(outputDir, { recursive: true });
await writeFile(outputFile, `${JSON.stringify(tasks, null, 2)}\n`);
console.log(`Generated ${tasks.length} task records.`);
