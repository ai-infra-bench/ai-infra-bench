'use client';

import { useMemo, useState } from 'react';
import Image from 'next/image';
import { withBasePath, withRouteBasePath } from '@/app/lib/base-path';
import { formatLabel, formatProjectName, formatTaskHardware, formatTaskTitle } from '@/app/lib/task-format';

type TaskSummary = {
  slug: string;
  description: string;
  taskType: string | null;
  keywords: string[];
  repository: string | null;
  repositoryName: string | null;
  repositoryLogo: string | null;
  repositoryLogoKind: 'mark' | 'wordmark' | null;
  gpus: number;
  gpuTypes: string[];
};

function RepositoryBrand({ task }: { task: TaskSummary }) {
  const [failed, setFailed] = useState(false);
  const name = task.repositoryName ?? formatProjectName(task.repository);

  if (!task.repositoryLogo || failed) {
    return <span className="task-repository-text">{name}</span>;
  }

  return (
    <Image
      className={`task-repository-logo is-${task.repositoryLogoKind ?? 'wordmark'}`}
      src={withBasePath(task.repositoryLogo)}
      alt={name}
      width={144}
      height={40}
      unoptimized
      onError={() => setFailed(true)}
    />
  );
}

export function TaskExplorer({ tasks }: { tasks: TaskSummary[] }) {
  const [hardware, setHardware] = useState('all');

  const hardwareOptions = useMemo(
    () => Array.from(new Set(tasks.map(formatTaskHardware))),
    [tasks],
  );

  const visibleTasks = useMemo(() => {
    return tasks.filter((task) => hardware === 'all' || formatTaskHardware(task) === hardware);
  }, [hardware, tasks]);

  return (
    <section className="home-section task-catalog" id="tasks" aria-labelledby="task-catalog-title">
      <div className="catalog-intro scroll-reveal">
        <h2 className="home-section-title" id="task-catalog-title">Tasks</h2>
        <p>
          {tasks.length} offline tasks with execution-based behavioral and e2e tests.
        </p>
      </div>

      <div className="catalog-tools">
        <div className="accelerator-filter" aria-label="Filter tasks by hardware">
          {['all', ...hardwareOptions].map((option) => (
            <button
              type="button"
              key={option}
              onClick={() => setHardware(option)}
              className={hardware === option ? 'is-active' : ''}
              aria-pressed={hardware === option}
            >
              {option === 'all' ? 'All' : option}
            </button>
          ))}
        </div>
      </div>

      <div className="task-cards">
        {visibleTasks.map((task) => (
          <a className="task-card scroll-reveal-card" href={withRouteBasePath(`/tasks/${task.slug}`)} key={task.slug}>
            <div className="task-primary">
              <span className="task-repository">
                <RepositoryBrand task={task} />
              </span>
              <h3>{formatTaskTitle(task.slug)}</h3>
              <p>{task.description}</p>
            </div>
            <footer className="task-card-meta">
              <span>{formatLabel(task.taskType)}</span>
              <span>{task.keywords.slice(1).join(', ')}</span>
              <span className="task-accelerator">{formatTaskHardware(task)}</span>
            </footer>
          </a>
        ))}
      </div>

      {visibleTasks.length === 0 && (
        <div className="empty-state">
          <p>No tasks match the current filters.</p>
          <button
            type="button"
            onClick={() => {
              setHardware('all');
            }}
          >
            Clear filters
          </button>
        </div>
      )}
    </section>
  );
}
