import { ArrowRightIcon } from "@radix-ui/react-icons";
import type { TaskSummary } from "@/app/lib/tasks";
import { withRouteBasePath } from "@/app/lib/base-path";
import { formatLabel, formatTaskTitle } from "@/app/lib/task-format";

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
      data-workload={formatLabel(task.workloadType).toLowerCase()}
      href={withRouteBasePath("/tasks/" + task.slug)}
    >
      <span className="catalogue-ordinal" aria-hidden="true">
        {String(ordinal).padStart(2, "0")}
      </span>
      <div className="catalogue-card-head">
        <span className="catalogue-kind">{formatLabel(task.workloadType)}</span>
        {showHardware && (
          <span className="catalogue-hardware">{task.accelerator}</span>
        )}
      </div>
      <div className="catalogue-copy">
        <Heading>{formatTaskTitle(task.slug)}</Heading>
        <p>{task.description}</p>
      </div>
      <div className="catalogue-card-foot">
        <span className="catalogue-subsystems">
          {task.subsystems.map(formatLabel).join(", ")}
        </span>
        <ArrowRightIcon aria-hidden="true" />
      </div>
    </a>
  );
}
