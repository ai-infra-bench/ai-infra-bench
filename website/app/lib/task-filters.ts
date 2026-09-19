import type { TaskSummary } from "./tasks";

export type TaskDomain = "inference" | "training" | "agent_harness";
export const DOMAIN_LABELS: Record<TaskDomain, string> = {
  inference: "Inference",
  training: "Training",
  agent_harness: "Agent harness",
};
// Project and domain are different dimensions. Only explicitly classified
// projects get a fallback; unknown projects are never assumed to be inference.
const PROJECT_DOMAINS: Readonly<Record<string, TaskDomain>> = {
  "vllm-project/vllm": "inference",
};
export function taskDomain(
  task: Pick<TaskSummary, "repository" | "domain">,
): TaskDomain | null {
  if (task.domain)
    return Object.hasOwn(DOMAIN_LABELS, task.domain)
      ? (task.domain as TaskDomain)
      : null;
  return task.repository && Object.hasOwn(PROJECT_DOMAINS, task.repository)
    ? PROJECT_DOMAINS[task.repository]
    : null;
}
export function availableDomains(tasks: TaskSummary[]) {
  return (Object.keys(DOMAIN_LABELS) as TaskDomain[]).filter((domain) =>
    tasks.some((task) => taskDomain(task) === domain),
  );
}

export type FilterState = {
  q: string;
  workload: string;
  domain: "all" | TaskDomain;
  page: number;
};
export const DEFAULT_FILTERS: FilterState = {
  q: "",
  workload: "all",
  domain: "all",
  page: 1,
};
export function workloadKey(value: string | null) {
  return (
    value
      ?.trim()
      .toLowerCase()
      .replace(/[\s_-]+/g, "") || "unknown"
  );
}
function text(value: string) {
  return value.normalize("NFKC").toLowerCase().replace(/[_-]+/g, " ");
}

export function filterTasks(tasks: TaskSummary[], state: FilterState) {
  const words = text(state.q).trim().split(/\s+/).filter(Boolean);
  return tasks
    .filter((task) => {
      if (
        state.workload !== "all" &&
        workloadKey(task.workloadType) !== state.workload
      )
        return false;
      const domain = taskDomain(task);
      if (state.domain !== "all" && domain !== state.domain) return false;
      const haystack = text(
        [
          task.name,
          task.slug,
          task.description,
          ...task.keywords,
          ...task.subsystems,
          task.repository ?? "",
          task.accelerator ?? "",
          domain ? DOMAIN_LABELS[domain] : "",
        ].join(" "),
      );
      return words.every((word) => haystack.includes(word));
    })
    .sort((a, b) => a.slug.localeCompare(b.slug, "en"));
}
export function paginateTasks<T>(
  tasks: T[],
  requestedPage: number,
  pageSize: number,
) {
  const size = Number.isSafeInteger(pageSize) && pageSize > 0 ? pageSize : 8;
  const pageCount = Math.max(1, Math.ceil(tasks.length / size));
  const page = Math.min(
    pageCount,
    Math.max(1, Number.isSafeInteger(requestedPage) ? requestedPage : 1),
  );
  const start = (page - 1) * size;
  return {
    page,
    pageCount,
    start,
    end: Math.min(start + size, tasks.length),
    items: tasks.slice(start, start + size),
  };
}
export function readFilters(search: string, tasks: TaskSummary[]): FilterState {
  const params = new URLSearchParams(search);
  const workloads = new Set(tasks.map((t) => workloadKey(t.workloadType)));
  const workload = workloadKey(params.get("type"));
  const domain = params.get("domain") as TaskDomain;
  const rawPage = params.get("page") ?? "1",
    page = /^\d+$/.test(rawPage) ? Number(rawPage) : 1;
  return {
    q: params.get("q") ?? "",
    workload: workloads.has(workload) ? workload : "all",
    domain: availableDomains(tasks).includes(domain) ? domain : "all",
    page: Number.isSafeInteger(page) && page > 0 ? page : 1,
  };
}
export function writeFilters(state: FilterState, existingSearch = "") {
  const params = new URLSearchParams(existingSearch);
  // Retired filters must not survive as invisible state in bookmarked URLs.
  for (const key of [
    "q",
    "type",
    "domain",
    "page",
    "subsystem",
    "result",
    "sort",
    "set",
  ])
    params.delete(key);
  if (state.q) params.set("q", state.q);
  if (state.workload !== "all") params.set("type", state.workload);
  if (state.domain !== "all") params.set("domain", state.domain);
  if (state.page > 1) params.set("page", String(state.page));
  const query = params.toString();
  return query ? "?" + query : "";
}
export function hasFilters(state: FilterState) {
  return Boolean(state.q || state.workload !== "all" || state.domain !== "all");
}
