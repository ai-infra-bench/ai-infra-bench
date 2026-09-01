import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { SiteHeader } from '@/app/components/site-header';
import { TaskContentTabs } from '@/app/components/task-content-tabs';
import { formatLabel, formatTaskTitle } from '@/app/lib/task-format';
import { tasks } from '@/app/lib/tasks';

type TaskPageProps = {
  params: Promise<{ slug: string }>;
};

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
  const memoryGb = task.memoryMb ? Math.round(task.memoryMb / 1024) : null;

  return (
    <main className="task-page">
      <SiteHeader />

      <article className="task-detail">
        <header className="task-detail-heading">
          <Link href="/#tasks">Back to tasks</Link>
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
        />

        <details className="environment-details">
          <summary>Environment</summary>
          <dl>
            <div>
              <dt>Agent timeout</dt>
              <dd>{task.agentTimeoutSec ? `${task.agentTimeoutSec / 60} min` : 'Not specified'}</dd>
            </div>
            <div>
              <dt>Verifier timeout</dt>
              <dd>{task.verifierTimeoutSec ? `${task.verifierTimeoutSec / 60} min` : 'Not specified'}</dd>
            </div>
            <div>
              <dt>CPU</dt>
              <dd>{task.cpus ? `${task.cpus} cores` : 'Not specified'}</dd>
            </div>
            <div>
              <dt>Memory</dt>
              <dd>{memoryGb ? `${memoryGb} GB` : 'Not specified'}</dd>
            </div>
            <div>
              <dt>Network</dt>
              <dd>{formatLabel(task.networkMode)}</dd>
            </div>
            <div>
              <dt>Track</dt>
              <dd>{formatLabel(task.track)}</dd>
            </div>
          </dl>
        </details>

        <nav className="task-pagination" aria-label="Adjacent tasks">
          <div>
            {previous && (
              <Link href={`/tasks/${previous.slug}`}>
                <span>Previous task</span>
                {formatTaskTitle(previous.slug)}
              </Link>
            )}
          </div>
          <div>
            {next && (
              <Link href={`/tasks/${next.slug}`}>
                <span>Next task</span>
                {formatTaskTitle(next.slug)}
              </Link>
            )}
          </div>
        </nav>
      </article>
    </main>
  );
}
