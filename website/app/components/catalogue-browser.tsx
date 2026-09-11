"use client";

import { useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  ChevronDownIcon,
  Cross2Icon,
  MagnifyingGlassIcon,
} from "@radix-ui/react-icons";
import type { TaskSummary } from "@/app/lib/tasks";
import { formatLabel } from "@/app/lib/task-format";
import {
  availableDomains,
  DOMAIN_LABELS,
  filterTasks,
  paginateTasks,
  readFilters,
  workloadKey,
  writeFilters,
  type FilterState,
} from "@/app/lib/task-filters";
import { TaskEntry } from "@/app/components/task-entry";

const changed = "ai-infra-task-filter-change";
function subscribe(listener: () => void) {
  window.addEventListener("popstate", listener);
  window.addEventListener(changed, listener);
  return () => {
    window.removeEventListener("popstate", listener);
    window.removeEventListener(changed, listener);
  };
}
const snapshot = () => window.location.search;
const serverSnapshot = () => "";
type Option = { value: string; label: string; count: number };

function SearchField({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const id = useId(),
    input = useRef<HTMLInputElement>(null);
  return (
    <div className="explorer-field explorer-search-field">
      <label className="explorer-label" htmlFor={id}>
        Search tasks
      </label>
      <div className="explorer-search">
        <MagnifyingGlassIcon aria-hidden="true" />
        <input
          ref={input}
          id={id}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Title, description or keyword"
          autoComplete="off"
        />
        {value && (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => {
              onChange("");
              input.current?.focus();
            }}
          >
            <Cross2Icon aria-hidden="true" />
          </button>
        )}
      </div>
    </div>
  );
}
function ChoiceFacet({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
}) {
  const id = useId();
  return (
    <fieldset className="explorer-radio">
      <legend>{label}</legend>
      {options.map((option) => (
        <label key={option.value}>
          <input
            type="radio"
            name={id}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
          />
          <span>{option.label}</span>
          <small aria-hidden="true">{option.count}</small>
        </label>
      ))}
    </fieldset>
  );
}

export function CatalogueBrowser({
  tasks,
  pageSize = 8,
}: {
  tasks: TaskSummary[];
  pageSize?: number;
}) {
  const search = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  const state = useMemo(() => readFilters(search, tasks), [search, tasks]);
  const section = useRef<HTMLElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const sidebarId = useId();
  const filtered = useMemo(() => filterTasks(tasks, state), [tasks, state]);
  const page = paginateTasks(filtered, state.page, pageSize);
  const workOptions = [
    { value: "all", label: "All" },
    ...[...new Set(tasks.map((t) => workloadKey(t.workloadType)))]
      .sort()
      .map((value) => ({
        value,
        label: formatLabel(
          tasks.find((t) => workloadKey(t.workloadType) === value)!
            .workloadType,
        ),
      })),
  ].map((option) => ({
    ...option,
    count: filterTasks(tasks, { ...state, workload: option.value }).length,
  }));
  const domainOptions = [
    { value: "all", label: "All" },
    ...availableDomains(tasks).map((value) => ({
      value,
      label: DOMAIN_LABELS[value],
    })),
  ].map((option) => ({
    ...option,
    count: filterTasks(tasks, {
      ...state,
      domain: option.value as FilterState["domain"],
    }).length,
  }));
  const facetCount =
    Number(state.workload !== "all") + Number(state.domain !== "all");
  const update = (patch: Partial<FilterState>, pageChange = false) => {
    const next = { ...state, page: 1, ...patch };
    const url =
      window.location.pathname +
      writeFilters(next, window.location.search) +
      window.location.hash;
    window.history[pageChange ? "pushState" : "replaceState"](
      window.history.state,
      "",
      url,
    );
    window.dispatchEvent(new Event(changed));
    if (pageChange)
      requestAnimationFrame(() =>
        section.current?.scrollIntoView({
          block: "start",
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
            .matches
            ? "instant"
            : "smooth",
        }),
      );
  };

  return (
    <section
      ref={section}
      className="design-tasks catalogue catalogue-collection catalogue-advanced explorer-design-sidebar"
      data-catalogue-layout="sidebar"
      id="tasks"
      aria-labelledby="tasks-title"
    >
      <div className="catalogue-introduction">
        <header className="tasks-heading">
          <h1 id="tasks-title">Tasks</h1>
          <p>
            {tasks.length} offline tasks with execution-based behavioral and e2e
            tests.
          </p>
        </header>
      </div>
      <div className="explorer-workspace">
        <aside className="explorer-sidebar" aria-label="Task filters">
          <button
            type="button"
            className="explorer-sidebar-toggle"
            aria-expanded={sidebarOpen}
            aria-controls={sidebarId}
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            Filters
            {facetCount > 0 && (
              <span className="explorer-filter-count">({facetCount})</span>
            )}
            <ChevronDownIcon aria-hidden="true" />
          </button>
          <div
            id={sidebarId}
            className="explorer-sidebar-panel"
            data-open={sidebarOpen}
          >
            <ChoiceFacet
              label="Work type"
              value={state.workload}
              options={workOptions}
              onChange={(workload) => update({ workload })}
            />
            <ChoiceFacet
              label="Domain"
              value={state.domain}
              options={domainOptions}
              onChange={(domain) =>
                update({ domain: domain as FilterState["domain"] })
              }
            />
          </div>
        </aside>
        <div className="explorer-content">
          <SearchField value={state.q} onChange={(q) => update({ q })} />
          {page.items.length ? (
            <div className="catalogue-grid">
              {page.items.map((task) => (
                <TaskEntry
                  key={task.slug}
                  task={task}
                  ordinal={tasks.indexOf(task) + 1}
                  showHardware={
                    new Set(tasks.map((t) => t.accelerator)).size > 1
                  }
                  headingLevel="h2"
                />
              ))}
            </div>
          ) : (
            <div className="explorer-empty" role="status">
              <h2>No matching tasks</h2>
              <p>Try another keyword or filter.</p>
            </div>
          )}
          {page.pageCount > 1 && (
            <nav className="catalogue-pagination" aria-label="Task pagination">
              <div className="catalogue-page-numbers">
                {Array.from({ length: page.pageCount }, (_, i) => i + 1).map(
                  (number) => (
                    <button
                      key={number}
                      type="button"
                      aria-label={"Task page " + number}
                      aria-current={number === page.page ? "page" : undefined}
                      onClick={() => update({ page: number }, true)}
                    >
                      {number}
                    </button>
                  ),
                )}
              </div>
            </nav>
          )}
          {filtered.length > 0 && (
            <p className="sr-only" role="status">
              {filtered.length} matching tasks. Page {page.page} of{" "}
              {page.pageCount}. Showing tasks {page.start + 1} to {page.end}.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
