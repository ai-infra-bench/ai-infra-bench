"use client";

import { useRef, useState } from "react";
import type { TaskSummary } from "@/app/lib/tasks";
import { TaskEntry } from "@/app/components/task-entry";

export function HomeTasks({ tasks }: { tasks: TaskSummary[] }) {
  const sectionRef = useRef<HTMLElement>(null);
  const [page, setPage] = useState(1);
  const options = [
    ...new Set(
      tasks.map((t) => t.accelerator).filter((v): v is string => Boolean(v)),
    ),
  ];
  const perPage = 6;
  const pageCount = Math.max(1, Math.ceil(tasks.length / perPage));
  const currentPage = Math.min(page, pageCount);
  const visible = tasks.slice((currentPage - 1) * perPage, currentPage * perPage);
  const changePage = (nextPage: number) => {
    setPage(Math.min(pageCount, Math.max(1, nextPage)));
    requestAnimationFrame(() =>
      sectionRef.current?.scrollIntoView({
        block: "start",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      }),
    );
  };
  const entries = visible.map((task) => (
    <TaskEntry
      key={task.slug}
      task={task}
      ordinal={tasks.indexOf(task) + 1}
      showHardware={options.length > 1}
      headingLevel="h3"
    />
  ));
  return (
    <section
      ref={sectionRef}
      className="design-tasks catalogue catalogue-collection"
      id="tasks"
      aria-labelledby="tasks-title"
    >
      <div className="catalogue-introduction">
        <header className="tasks-heading">
          <h2 id="tasks-title">Tasks</h2>
          <p>
            {tasks.length} offline tasks with execution-based behavioral and e2e
            tests.
          </p>
        </header>
      </div>
      <div className="catalogue-grid">{entries}</div>
      {pageCount > 1 && (
        <nav className="catalogue-pagination" aria-label="Task pagination">
          <div className="catalogue-page-numbers">
            {Array.from({ length: pageCount }, (_, i) => i + 1).map(
              (number) => (
                <button
                  type="button"
                  key={number}
                  aria-label={"Task page " + number}
                  aria-current={currentPage === number ? "page" : undefined}
                  onClick={() => changePage(number)}
                >
                  {number}
                </button>
              ),
            )}
          </div>
        </nav>
      )}
      {tasks.length > 0 && (
        <p className="sr-only" role="status">
          Page {currentPage} of {pageCount}. Showing tasks{" "}
          {(currentPage - 1) * perPage + 1} to{" "}
          {Math.min(currentPage * perPage, tasks.length)} of{" "}
          {tasks.length}.
        </p>
      )}
      {visible.length === 0 && (
        <p className="empty-state">No tasks match the current filters.</p>
      )}
    </section>
  );
}
