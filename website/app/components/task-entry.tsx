import { ArrowRightIcon } from "@radix-ui/react-icons";
import type { TaskSummary } from "@/app/lib/tasks";
import { withRouteBasePath } from "@/app/lib/base-path";
import { formatLabel, formatTaskHardware, formatTaskTitle } from "@/app/lib/task-format";

export function TaskEntry({
  task,
  ordinal,
  showHardware,
  headingLevel,
}: {
  task: TaskSummary;
  ordinal: number;
  showHardware: boolean;
  headingLevel: "h2" | "h3";
}) {
  const Heading = headingLevel;
  return (
    <a
      className="catalogue-card"
      data-workload={formatLabel(task.taskType).toLowerCase()}
      href={withRouteBasePath("/tasks/" + task.slug)}
    >
      <span className="catalogue-ordinal" aria-hidden="true">
        {String(ordinal).padStart(2, "0")}
      </span>
      <div className="catalogue-card-head">
        <span className="catalogue-kind">{formatLabel(task.taskType)}</span>
        {showHardware && (
          <span className="catalogue-hardware">{formatTaskHardware(task)}</span>
        )}
      </div>
      <div className="catalogue-copy">
        <Heading>{formatTaskTitle(task.slug)}</Heading>
        <p>{task.description}</p>
      </div>
      <div className="catalogue-card-foot">
        <span className="catalogue-keywords">
          {task.keywords.slice(1).join(", ")}
        </span>
        <ArrowRightIcon aria-hidden="true" />
      </div>
    </a>
  );
}
