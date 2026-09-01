import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeftIcon, ArrowRightIcon } from '@radix-ui/react-icons';
import { SiteHeader } from '@/app/components/site-header';
import { TaskContentTabs } from '@/app/components/task-content-tabs';
import { formatTaskTitle } from '@/app/lib/task-format';
import { tasks, type ManifestSection, type ManifestValue } from '@/app/lib/tasks';

type TaskPageProps = {
  params: Promise<{ slug: string }>;
};

const metadataLabels: Record<string, string> = {
  base_commit: 'Base commit',
  benchmark_schema_version: 'Benchmark schema',
  build_timeout_sec: 'Build timeout',
  checkpoint_digests: 'Checkpoint digests',
  cpus: 'CPUs',
  dependency_cutoff: 'Dependency cutoff',
  dependency_cutoff_overrides: 'Dependency overrides',
  environment_mode: 'Environment mode',
  environment_template: 'Environment template',
  gpu_types: 'GPU types',
  gpus: 'GPUs',
  image_digest: 'Image digest',
  memory_mb: 'Memory',
  network_mode: 'Network',
  publication_state: 'Publication state',
  source_cutoff: 'Source cutoff',
  source_ids: 'Source IDs',
  storage_mb: 'Storage',
  task_version: 'Task version',
  timeout_sec: 'Timeout',
  user: 'User',
  workdir: 'Working directory',
};

function metadataLabel(key: string) {
  return metadataLabels[key] ?? key.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function metadataValue(key: string, value: ManifestValue) {
  if (value === null || value === '') return 'Not specified';
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'None';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number' && key.endsWith('_mb')) {
    return value % 1024 === 0 ? `${value / 1024} GB` : `${value} MB`;
  }
  if (typeof value === 'number' && key.endsWith('_sec')) {
    return value % 60 === 0 ? `${value / 60} min` : `${value} sec`;
  }
  return String(value);
}

function sectionFacts(section: ManifestSection, priority: string[], prefix = '') {
  const ordered = [
    ...priority.filter((key) => Object.hasOwn(section, key)),
    ...Object.keys(section).filter((key) => !priority.includes(key)).sort(),
  ];

  return ordered.map((key) => [
    prefix ? `${prefix} ${metadataLabel(key)}` : metadataLabel(key),
    metadataValue(key, section[key]),
  ] as [string, string]);
}

export function generateStaticParams() {
  return tasks.map((task) => ({ slug: task.slug }));
}

export async function generateMetadata({ params }: TaskPageProps): Promise<Metadata> {
  const { slug } = await params;
  const task = tasks.find((candidate) => candidate.slug === slug);
  if (!task) return {};

  const title = `${formatTaskTitle(task.slug)} | AI Infra Bench`;
  return {
    title,
    description: task.description,
    openGraph: { title, description: task.description, images: [] },
    twitter: { card: 'summary', title, description: task.description, images: [] },
  };
}

export default async function TaskPage({ params }: TaskPageProps) {
  const { slug } = await params;
  const index = tasks.findIndex((candidate) => candidate.slug === slug);
  if (index === -1) notFound();

  const task = tasks[index];
  const previous = index > 0 ? tasks[index - 1] : null;
  const next = index < tasks.length - 1 ? tasks[index + 1] : null;
  const compute = { ...task.manifest.environment };
  if (!Object.hasOwn(compute, 'topology')) {
    compute.topology = task.accelerator === 'CPU' ? 'Not applicable' : null;
  }

  const taskKeys = ['workload_type', 'subsystems'];
  const taskMetadata = Object.fromEntries(
    taskKeys
      .filter((key) => Object.hasOwn(task.manifest.metadata, key))
      .map((key) => [key, task.manifest.metadata[key]]),
  ) as ManifestSection;
  const metadataGroups = [
    { title: 'Task', facts: sectionFacts(taskMetadata, taskKeys) },
    {
      title: 'Compute',
      facts: sectionFacts(compute, [
        'accelerator', 'topology', 'gpus', 'gpu_types', 'cpus', 'memory_mb',
        'storage_mb', 'os', 'network_mode', 'workdir', 'build_timeout_sec',
      ]),
    },
    {
      title: 'Execution',
      facts: [
        ...sectionFacts(task.manifest.agent, ['timeout_sec', 'user', 'network_mode'], 'Agent'),
        ...sectionFacts(task.manifest.verifier, ['timeout_sec', 'environment_mode'], 'Verifier'),
      ],
    },
  ].filter((group) => group.facts.length > 0);

  return (
    <main className="task-page">
      <SiteHeader />

      <article className="task-detail">
        <header className="task-detail-heading">
          <h1>{formatTaskTitle(task.slug)}</h1>
          <p>{task.description}</p>
        </header>

        <TaskContentTabs
          instructionHtml={task.instructionHtml}
          verifierFiles={task.verifierFiles.map(({ name, highlightedHtml, lineCount }) => ({
            name,
            highlightedHtml,
            lineCount,
          }))}
          solutionFiles={task.solutionFiles.map(({ name, highlightedHtml, lineCount }) => ({
            name,
            highlightedHtml,
            lineCount,
          }))}
          environmentFiles={task.environmentFiles.map(({ name, highlightedHtml, lineCount }) => ({
            name,
            highlightedHtml,
            lineCount,
          }))}
          metadataGroups={metadataGroups}
        />

      </article>

      <nav className="task-sequence-nav" aria-label="Adjacent tasks">
        <div>
          {previous && (
            <Link href={`/tasks/${previous.slug}`}>
              <ArrowLeftIcon aria-hidden="true" />
              <span className="sequence-direction">Previous</span>
              <span className="sequence-title">{formatTaskTitle(previous.slug)}</span>
            </Link>
          )}
        </div>
        <div>
          {next && (
            <Link href={`/tasks/${next.slug}`}>
              <span className="sequence-title">{formatTaskTitle(next.slug)}</span>
              <span className="sequence-direction">Next</span>
              <ArrowRightIcon aria-hidden="true" />
            </Link>
          )}
        </div>
      </nav>
    </main>
  );
}
