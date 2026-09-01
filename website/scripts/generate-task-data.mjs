import { mkdir, readdir, readFile, rm, writeFile } from 'node:fs/promises';
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
const legacyOutputFile = path.join(outputDir, 'tasks.json');
const indexOutputFile = path.join(outputDir, 'task-index.json');
const detailsOutputDir = path.join(outputDir, 'task-details');
const loadersOutputFile = path.join(outputDir, 'task-loaders.ts');
const publicTaskFilesDir = path.join(projectDir, 'public', 'generated', 'task-files');

const paperTheme = {
  name: 'ai-infra-paper',
  type: 'light',
  colors: {
    'editor.background': '#F8F7F3',
    'editor.foreground': '#303638',
  },
  tokenColors: [
    {
      scope: ['comment', 'punctuation.definition.comment'],
      settings: { foreground: '#686D67', fontStyle: 'italic' },
    },
    {
      scope: ['string', 'string.quoted', 'markup.deleted', 'punctuation.definition.string'],
      settings: { foreground: '#8D4B43' },
    },
    {
      scope: ['keyword', 'storage', 'markup.inserted'],
      settings: { foreground: '#3F6D55' },
    },
    {
      scope: ['constant.numeric', 'constant.language', 'constant.character'],
      settings: { foreground: '#2D6F7A' },
    },
    {
      scope: ['entity.name.function', 'support.function'],
      settings: { foreground: '#806D1A' },
    },
    {
      scope: ['entity.name.type', 'entity.name.class', 'support.type'],
      settings: { foreground: '#6E5C8A' },
    },
    {
      scope: ['variable.parameter', 'meta.diff.header'],
      settings: { foreground: '#6E5C8A' },
    },
    {
      scope: ['punctuation', 'meta.brace'],
      settings: { foreground: '#686D67' },
    },
  ],
};

const highlighter = await createHighlighter({
  themes: [paperTheme],
  langs: ['bash', 'c', 'diff', 'dockerfile', 'json', 'python', 'text'],
});

function languageForFile(name) {
  if (path.basename(name).toLowerCase() === 'dockerfile') return 'dockerfile';
  if (name.endsWith('.sh')) return 'bash';
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.c')) return 'c';
  if (name.endsWith('.json')) return 'json';
  if (name.endsWith('.patch') || name.endsWith('.diff')) return 'diff';
  return 'text';
}

function highlightCode(content, language) {
  return highlighter.codeToHtml(content, {
    lang: language,
    theme: 'ai-infra-paper',
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
      theme: 'ai-infra-paper',
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

async function emitSourceFiles(taskSlug, group, files) {
  const groupDir = path.join(publicTaskFilesDir, taskSlug, group);
  await mkdir(groupDir, { recursive: true });

  return Promise.all(files.map(async (file, index) => {
    const highlightedHtml = highlightCode(file.content, languageForFile(file.name));
    const lineCount = file.content ? file.content.split(/\r?\n/).length : 0;
    const fileName = `${index}.json`;
    await writeFile(
      path.join(groupDir, fileName),
      `${JSON.stringify({ highlightedHtml, lineCount })}\n`,
    );
    return {
      name: file.name,
      lineCount,
      url: `/generated/task-files/${taskSlug}/${group}/${fileName}`,
    };
  }));
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
  const lines = source.split(/\r?\n/);
  const start = lines.findIndex((line) => new RegExp(`^${key}\\s*=`).test(line.trim()));
  if (start === -1) return null;

  let raw = lines[start].slice(lines[start].indexOf('=') + 1).trim();
  if (raw.startsWith('[')) {
    let depth = (raw.match(/\[/g) ?? []).length - (raw.match(/\]/g) ?? []).length;
    let index = start + 1;
    while (depth > 0 && index < lines.length) {
      raw += `\n${lines[index]}`;
      depth += (lines[index].match(/\[/g) ?? []).length;
      depth -= (lines[index].match(/\]/g) ?? []).length;
      index += 1;
    }
  }

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

function getSectionObject(source, name) {
  const section = getSection(source, name);
  const keys = Array.from(section.matchAll(/^([a-zA-Z0-9_]+)\s*=/gm), (match) => match[1]);
  return Object.fromEntries(keys.map((key) => [key, getValue(section, key)]));
}

await rm(detailsOutputDir, { recursive: true, force: true });
await rm(publicTaskFilesDir, { recursive: true, force: true });
await mkdir(detailsOutputDir, { recursive: true });
await mkdir(publicTaskFilesDir, { recursive: true });

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
  const environmentFiles = prioritizeFiles(
    await readTextFiles(path.join(taskDir, 'environment')),
    ['Dockerfile'],
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
    manifest: {
      schemaVersion: getValue(manifest, 'schema_version'),
      taskVersion: getValue(task, 'version'),
      metadata: getSectionObject(manifest, 'metadata'),
      agent: getSectionObject(manifest, 'agent'),
      environment: getSectionObject(manifest, 'environment'),
      verifier: getSectionObject(manifest, 'verifier'),
    },
    instructionHtml: await renderInstruction(instruction.trim()),
    verifierFiles: await emitSourceFiles(entry.name, 'tests', verifierFiles),
    solutionFiles: await emitSourceFiles(entry.name, 'solution', solutionFiles),
    environmentFiles: await emitSourceFiles(entry.name, 'environment', environmentFiles),
  });
}

tasks.sort((a, b) => a.slug.localeCompare(b.slug));

await mkdir(outputDir, { recursive: true });
await rm(legacyOutputFile, { force: true });

await Promise.all(tasks.map((task) => writeFile(
  path.join(detailsOutputDir, `${task.slug}.json`),
  `${JSON.stringify(task, null, 2)}\n`,
)));

const taskIndex = tasks.map((task) => ({
  slug: task.slug,
  name: task.name,
  version: task.version,
  description: task.description,
  keywords: task.keywords,
  track: task.track,
  workloadType: task.workloadType,
  subsystems: task.subsystems,
  repository: task.repository,
  accelerator: task.accelerator,
}));
await writeFile(indexOutputFile, `${JSON.stringify(taskIndex, null, 2)}\n`);

const loaderEntries = tasks.map((task) => (
  `  ${JSON.stringify(task.slug)}: () => import('./task-details/${task.slug}.json'),`
)).join('\n');
await writeFile(
  loadersOutputFile,
  `export const taskLoaders = {\n${loaderEntries}\n} as const;\n`,
);
console.log(`Generated ${tasks.length} task records.`);
