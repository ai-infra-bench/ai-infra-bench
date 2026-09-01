'use client';

import { useMemo, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { formatLabel, formatProjectName, formatTaskTitle } from '@/app/lib/task-format';

type TaskSummary = {
  slug: string;
  description: string;
  workloadType: string | null;
  subsystems: string[];
  repository: string | null;
  repositoryName: string | null;
  repositoryLogo: string | null;
  accelerator: string | null;
};

export function TaskExplorer({ tasks }: { tasks: TaskSummary[] }) {
  const [workload, setWorkload] = useState('all');

  const workloads = useMemo(
    () => Array.from(new Set(tasks.map((task) => task.workloadType).filter(Boolean))) as string[],
    [tasks],
  );

  const visibleTasks = useMemo(() => {
    return tasks.filter((task) => workload === 'all' || task.workloadType === workload);
  }, [tasks, workload]);

  return (
    <section className="task-catalog" id="tasks" aria-labelledby="task-catalog-title">
      <div className="catalog-intro">
        <h2 id="task-catalog-title">Tasks</h2>
        <p>
          {tasks.length} pinned AI infrastructure tasks with offline environments and execution-based verification.
        </p>
      </div>

      <div className="catalog-tools">
        <div className="workload-filter" aria-label="Filter tasks by workload">
          {['all', ...workloads].map((option) => (
            <button
              type="button"
              key={option}
              onClick={() => setWorkload(option)}
              className={workload === option ? 'is-active' : ''}
              aria-pressed={workload === option}
            >
              {option === 'all' ? 'All' : formatLabel(option)}
            </button>
          ))}
        </div>
      </div>

      <div className="task-cards">
        {visibleTasks.map((task) => (
          <Link className="task-card" href={`/tasks/${task.slug}`} key={task.slug}>
            <div className="task-primary">
              <span className="task-repository">
                {task.repositoryLogo ? (
                  <Image
                    className="task-repository-logo"
                    src={task.repositoryLogo}
                    alt={task.repositoryName ?? formatProjectName(task.repository)}
                    width={144}
                    height={40}
                  />
                ) : (
                  <span className="task-repository-text">{formatProjectName(task.repository)}</span>
                )}
              </span>
              <h3>{formatTaskTitle(task.slug)}</h3>
              <p>{task.description}</p>
            </div>
            <footer className="task-card-meta">
              <span>{formatLabel(task.workloadType)}</span>
              <span>{task.subsystems.map(formatLabel).join(', ')}</span>
              <span className="task-accelerator">{task.accelerator}</span>
            </footer>
          </Link>
        ))}
      </div>

      {visibleTasks.length === 0 && (
        <div className="empty-state">
          <p>No tasks match the current filters.</p>
          <button
            type="button"
            onClick={() => {
              setWorkload('all');
            }}
          >
            Clear filters
          </button>
        </div>
      )}
    </section>
  );
}
