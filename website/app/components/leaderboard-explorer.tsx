'use client';

import { Fragment, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { ArrowDownIcon, ArrowUpIcon, ChevronRightIcon } from '@radix-ui/react-icons';
import { LeaderboardEfficiencyChart } from '@/app/components/leaderboard-efficiency-chart';
import { withRouteBasePath } from '@/app/lib/base-path';
import { modelColor } from '@/app/lib/leaderboard-chart';
import { formatTaskTitle } from '@/app/lib/task-format';

type TaskResult = { task: string; attempts: number; passes: number; costUsd: number };
type Configuration = {
  id: string;
  model: string;
  effort: string;
  agent: string;
  agentVersion: string;
  status: string;
  metrics: {
    passAverage: number | null;
    passAverageStd: number | null;
    repetitionPassRates: number[] | null;
    passAtK: number | null;
    passedTrials: number;
    validTrials: number;
    expectedTrials: number;
    tasksPassed: number;
    taskCount: number;
    completeTasks: number;
    totalCostUsd: number | null;
    averageCostUsd: number | null;
    averageTurns: number | null;
    averageToolCalls: number | null;
    averageOutputTokens: number | null;
    averageDurationMinutes: number | null;
  };
  tasks: TaskResult[];
};

type LeaderboardData = {
  release: {
    expectedAttempts: number;
    validTrials: number;
    expectedTrials: number;
    status: string;
  };
  configurations: Configuration[];
};

type SortKey = 'passAverage' | 'passAtK' | 'totalCostUsd' | 'averageTurns' | 'averageToolCalls';

function percentage(value: number | null) {
  return value === null ? 'N/A' : value.toFixed(1) + '%';
}

function decimal(value: number | null, digits = 1) {
  return value === null ? 'N/A' : value.toFixed(digits);
}

function money(value: number | null) {
  return value === null ? 'N/A' : '$' + value.toFixed(2);
}

function passAverage(configuration: Configuration) {
  const { passAverage: mean, passAverageStd: std } = configuration.metrics;
  if (mean === null) return 'N/A';
  return std === null ? percentage(mean) : percentage(mean) + ' ± ' + percentage(std);
}

export function LeaderboardExplorer({ data }: { data: LeaderboardData }) {
  const [sortKey, setSortKey] = useState<SortKey>('passAverage');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [expanded, setExpanded] = useState<string | null>(null);
  const attempts = data.release.expectedAttempts;

  const sorted = useMemo(() => {
    const sign = sortDirection === 'desc' ? -1 : 1;
    return [...data.configurations].sort((a, b) => {
      const left = a.metrics[sortKey];
      const right = b.metrics[sortKey];
      if (left === null) return right === null ? a.id.localeCompare(b.id) : 1;
      if (right === null) return -1;
      return (left - right) * sign || a.id.localeCompare(b.id);
    });
  }, [data.configurations, sortDirection, sortKey]);

  const changeSort = (key: SortKey) => {
    if (key === sortKey) setSortDirection((direction) => direction === 'desc' ? 'asc' : 'desc');
    else {
      setSortKey(key);
      setSortDirection(['totalCostUsd', 'averageTurns', 'averageToolCalls'].includes(key) ? 'asc' : 'desc');
    }
  };

  const columns: { key: SortKey; label: string }[] = [
    { key: 'passAverage', label: 'Pass avg' },
    { key: 'passAtK', label: 'Pass@' + attempts },
    { key: 'averageTurns', label: 'Avg turns' },
    { key: 'averageToolCalls', label: 'Avg tools' },
    { key: 'totalCostUsd', label: 'Total cost' },
  ];

  return (
    <>
      <LeaderboardEfficiencyChart configurations={data.configurations} />

      <section className="leaderboard-ledger" aria-labelledby="ledger-title">
        <div className="ledger-heading">
          <h3 id="ledger-title">All results</h3>
        </div>
        <div className="leaderboard-table-wrap" role="region" aria-label="Evaluation results" tabIndex={0}>
          <table className="leaderboard-table">
            <caption className="sr-only">Model results. Sort a column or expand a configuration to see its task-level results.</caption>
            <colgroup>
              <col className="column-expander" />
              <col span={columns.length + 3} />
            </colgroup>
            <thead>
              <tr>
                <th scope="col"><span className="sr-only">Task details</span></th>
                <th scope="col" className="column-model">Model</th>
                <th scope="col" className="column-text">Effort</th>
                <th scope="col" className="column-text">Agent</th>
                {columns.map((column) => (
                  <th key={column.key} scope="col"
                    aria-sort={sortKey === column.key ? (sortDirection === 'desc' ? 'descending' : 'ascending') : 'none'}>
                    <button type="button" className={sortKey === column.key ? 'is-active' : ''}
                      onClick={() => changeSort(column.key)}
                      title={column.key === 'passAverage' ? 'Mean ± sample standard deviation across ' + attempts + ' complete repetitions (ddof=1).' : undefined}>
                      <span>{column.label}</span>
                      {sortKey === column.key && sortDirection === 'asc'
                        ? <ArrowUpIcon aria-hidden="true" />
                        : <ArrowDownIcon aria-hidden="true" />}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((configuration) => {
                const isExpanded = expanded === configuration.id;
                const metrics = configuration.metrics;
                const detailsId = 'details-' + configuration.id;
                return (
                  <Fragment key={configuration.id}>
                    <tr className={'ledger-row' + (isExpanded ? ' is-expanded' : '')}>
                      <td>
                        <button className="row-expander" type="button"
                          aria-label={(isExpanded ? 'Hide' : 'Show') + ' task results for ' + configuration.model + ' ' + configuration.effort}
                          aria-expanded={isExpanded} aria-controls={isExpanded ? detailsId : undefined}
                          onClick={() => setExpanded(isExpanded ? null : configuration.id)}>
                          <ChevronRightIcon aria-hidden="true" />
                        </button>
                      </td>
                      <th scope="row" className="column-model">
                        <div className="ledger-model-name" style={{ '--series-color': modelColor(configuration.model) } as CSSProperties}>
                          <i className={'series-key' + (configuration.model === 'gpt-5.6-sol' ? ' is-square' : '')}
                            aria-hidden="true" />
                          <span>{configuration.model}</span>
                        </div>
                        <span className="mobile-model-effort" aria-hidden="true">{configuration.effort}</span>
                      </th>
                      <td className="column-text">{configuration.effort}</td>
                      <td className="column-text">{configuration.agent} {configuration.agentVersion}</td>
                      <td title={metrics.repetitionPassRates ? 'Repetition pass rates: ' + metrics.repetitionPassRates.map(percentage).join(', ') : 'Standard deviation requires complete repetitions.'}>{passAverage(configuration)}</td>
                      <td title={metrics.tasksPassed + '/' + metrics.taskCount + ' tasks solved'}>{percentage(metrics.passAtK)}</td>
                      <td>{decimal(metrics.averageTurns)}</td>
                      <td>{decimal(metrics.averageToolCalls)}</td>
                      <td>{money(metrics.totalCostUsd)}</td>
                    </tr>
                    {isExpanded && (
                      <tr className="task-breakdown-row">
                        <td colSpan={columns.length + 4} id={detailsId}>
                          <div className="configuration-panel">
                            <div className="task-breakdown-heading">
                              <h4>Task results</h4>
                            </div>
                            <div className="task-breakdown">
                              {configuration.tasks.map((task) => (
                                <div className="task-score" key={task.task}>
                                  <a href={withRouteBasePath('/tasks/' + task.task)}>{formatTaskTitle(task.task)}</a>
                                  <span className="attempt-dots" aria-label={task.passes + ' of ' + task.attempts + ' runs passed'}>
                                    {Array.from({ length: attempts }, (_, attempt) => (
                                      <i key={attempt} className={attempt < task.passes ? 'is-pass' : attempt < task.attempts ? 'is-fail' : 'is-missing'} />
                                    ))}
                                  </span>
                                  <strong title={money(task.costUsd) + ' total cost'}>{task.passes}/{task.attempts}</strong>
                                </div>
                              ))}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
