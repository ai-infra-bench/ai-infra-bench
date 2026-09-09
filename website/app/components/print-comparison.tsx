"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import {
  modelColor,
  placePlotLabels,
  type ChartConfiguration,
  type PlotPoint,
  effortOrder,
} from "@/app/lib/leaderboard-chart";
import {
  plotGroupKey,
  resolvePlotFocus,
  type PlotTarget,
} from "@/app/lib/plot-focus";
import { focusedDomain } from "@/app/lib/hero-plot";
import { curvePath, descendingLinear } from "@/app/lib/print-geometry";
import leaderboard from "@/app/generated/leaderboard.json";

type Axis = "cost" | "tokens" | "tools";
type PrintConfiguration = ChartConfiguration & {
  metrics: {
    passAverage: number;
    averageCostUsd: number;
    averageOutputTokens: number;
    averageToolCalls: number;
  };
};
const axisKeys = {
  cost: "averageCostUsd",
  tokens: "averageOutputTokens",
  tools: "averageToolCalls",
} as const;
const axisLabels = {
  cost: "Cost",
  tokens: "Output tokens",
  tools: "Tool calls",
};
const axisTitles = {
  cost: "Average cost per run (USD)",
  tokens: "Average output tokens per run",
  tools: "Average tool calls per run",
};
function format(n: number, axis: Axis, exact = false) {
  return axis === "cost"
    ? "$" + n.toFixed(exact ? 2 : Number.isInteger(n) ? 0 : 1)
    : axis === "tokens"
      ? exact
        ? Math.round(n).toLocaleString("en-US")
        : (n / 1000).toFixed(n % 1000 ? 1 : 0) + "k"
      : n.toFixed(exact ? 1 : 0);
}

export function PrintComparison() {
  const [axis, setAxis] = useState<Axis>("cost");
  const [hover, setHover] = useState<PlotTarget>(null);
  const [pinned, setPinned] = useState<PlotTarget>(null);
  const configs = useMemo(
    () =>
      [...leaderboard.configurations].sort(
        (a, b) => effortOrder.indexOf(a.effort) - effortOrder.indexOf(b.effort),
      ),
    [],
  );
  const { pointId, group } = resolvePlotFocus(configs, hover, pinned);
  const chosen = configs.find((c) => c.id === pointId),
    chosenSeries = configs.find((c) => plotGroupKey(c) === group);
  const dense = new Set(configs.map(plotGroupKey)).size > 3;
  const clear = () => {
    setHover(null);
    setPinned(null);
  };
  const pin = (target: NonNullable<PlotTarget>) =>
    setPinned((previous) =>
      previous?.kind === target.kind && previous.id === target.id
        ? null
        : target,
    );
  return (
    <figure
      className={
        "print-comparison mode-curve" + (dense ? " has-many-series" : "")
      }
      data-benchmark-scope="global"
      onKeyDown={(e) => {
        if (e.key === "Escape") clear();
      }}
    >
      <div className="print-toolbar">
        <span className="print-metric-label">Pass Average</span>
        <div
          className="print-axis-control"
          role="group"
          aria-label="Compare by"
        >
          {(["cost", "tokens", "tools"] as Axis[]).map((a) => (
            <button
              key={a}
              type="button"
              aria-pressed={axis === a}
              onClick={() => {
                setAxis(a);
                clear();
              }}
            >
              {axisLabels[a]}
            </button>
          ))}
        </div>
      </div>
      <div
        className="print-figures"
        role={dense ? "region" : undefined}
        aria-label={dense ? "Model comparison chart" : undefined}
        tabIndex={dense ? 0 : undefined}
      >
        <Chart
          configs={configs}
          axis={axis}
          selected={pointId}
          focusedGroup={group}
          pinned={pinned}
          onHover={setHover}
          onPin={pin}
        />
      </div>
      <figcaption className="print-caption">
        <div className="print-live" aria-live="polite">
          {chosen ? (
            <>
              <span>
                {chosen.model} <em>{chosen.effort}</em>
              </span>
              <span>{chosen.metrics.passAverage.toFixed(1)}% Pass Average</span>
              <span>
                {format(chosen.metrics[axisKeys[axis]], axis, true)} / run
              </span>
            </>
          ) : chosenSeries ? (
            <span>{chosenSeries.model}</span>
          ) : (
            <>
              <span>{leaderboard.release.taskCount} tasks</span>
              <span>{leaderboard.release.expectedAttempts} runs per task</span>
            </>
          )}
        </div>
        {pinned && (
          <button type="button" className="print-clear" onClick={clear}>
            Clear
          </button>
        )}
      </figcaption>
    </figure>
  );
}
function Chart({
  configs,
  axis,
  selected,
  focusedGroup,
  pinned,
  onHover,
  onPin,
}: {
  configs: PrintConfiguration[];
  axis: Axis;
  selected: string | null;
  focusedGroup: string | null;
  pinned: PlotTarget;
  onHover: (target: PlotTarget) => void;
  onPin: (target: NonNullable<PlotTarget>) => void;
}) {
  const ref = useRef<HTMLDivElement>(null),
    id = useId().replaceAll(":", "");
  const [size, setSize] = useState({ width: 1000, height: 440 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const resize = () => {
      const r = el.getBoundingClientRect();
      setSize((s) =>
        s.width === r.width && s.height === r.height
          ? s
          : { width: r.width, height: r.height },
      );
    };
    resize();
    const obs = new ResizeObserver(resize);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  const compact = size.width < 600,
    xd = focusedDomain(configs.map((c) => c.metrics[axisKeys[axis]]));
  const scores = configs.map((c) => c.metrics.passAverage);
  const yMin = Math.max(
    0,
    Math.floor((Math.min(...scores, 100) - 1) / 10) * 10,
  );
  const yMax = Math.min(
    100,
    Math.max(yMin + 10, Math.ceil((Math.max(...scores, 0) + 1) / 10) * 10),
  );
  const left = compact ? 40 : 48,
    right = compact ? 20 : 38,
    top = 34,
    bottom = size.height - 54;
  const width = Math.max(1, size.width - left - right),
    height = Math.max(1, bottom - top);
  const x = (n: number) => descendingLinear(n, xd.min, xd.max, left, width),
    y = (n: number) => bottom - ((n - yMin) / (yMax - yMin)) * height;
  const points: PlotPoint[] = configs.map((c) => ({
    configuration: c,
    value: c.metrics[axisKeys[axis]],
    score: c.metrics.passAverage,
    color: modelColor(c.model),
    group: plotGroupKey(c),
    x: x(c.metrics[axisKeys[axis]]),
    y: y(c.metrics.passAverage),
  }));
  const groups = [...new Set(points.map((p) => p.group))].map((key) =>
    points.filter((p) => p.group === key),
  );
  const selectedPoint = points.find((p) => p.configuration.id === selected);
  const labels = placePlotLabels(
    points,
    { x: left + 4, y: top + 4, width: width - 8, height: height - 8 },
    compact,
    selected,
  );
  const ticks = Array.from(
    { length: Math.round((yMax - yMin) / 10) + 1 },
    (_, i) => yMin + i * 10,
  );
  const muted = (key: string) => Boolean(focusedGroup && focusedGroup !== key);
  const curveColor = (key: string, color: string) =>
    muted(key) ? "var(--plot-muted-line)" : color;
  return (
    <div className="print-chart" ref={ref}>
      <svg
        viewBox={"0 0 " + size.width + " " + size.height}
        className="print-svg"
        role="group"
        aria-labelledby={id + "-title " + id + "-desc"}
        data-focused-group={focusedGroup ?? ""}
        data-axis={axis}
        data-score="passAverage"
        data-polar="false"
        data-x-direction="descending"
        data-x-min={xd.min}
        data-x-max={xd.max}
        data-y-min={yMin}
        data-y-max={yMax}
      >
        <title id={id + "-title"}>
          {"Pass Average (%) by " + axisLabels[axis]}
        </title>
        <desc id={id + "-desc"}>
          Both axes are linear with explicitly labeled ranges. Resource use
          decreases from left to right. {configs.length} plotted configurations.
          Hover or focus a curve to highlight its model; a point also projects
          to both axes. Curves guide reading, not prediction.
        </desc>
        <g className="print-coordinates">
          {ticks.map((t) => (
            <g key={t}>
              <path
                className="print-grid"
                d={"M" + left + " " + y(t) + " H" + (size.width - right)}
              />
              <text x={left - 13} y={y(t) + 4} textAnchor="end">
                {t}
              </text>
            </g>
          ))}
          <path
            className="print-baseline"
            d={
              "M" +
              left +
              " " +
              top +
              " V" +
              bottom +
              " H" +
              (size.width - right)
            }
          />
          {[...xd.ticks]
            .reverse()
            .filter(
              (_, i) => !compact || i % 2 === 0 || i === xd.ticks.length - 1,
            )
            .map((t) => (
              <g key={t} className="print-x-tick" data-value={t}>
                <path d={"M" + x(t) + " " + bottom + " v5"} />
                <text x={x(t)} y={bottom + 25} textAnchor="middle">
                  {format(t, axis)}
                </text>
              </g>
            ))}
        </g>
        {groups
          .filter((series) => series.length > 1)
          .map((series) => {
            const key = series[0].group,
              target = { kind: "series" as const, id: key },
              d = curvePath(series),
              color = curveColor(key, series[0].color);
            return (
              <g
                key={key}
                className="print-curve"
                data-series-group={key}
                data-muted={muted(key)}
                data-focused={focusedGroup === key}
              >
                <path
                  className="print-series underprint"
                  d={d}
                  style={{ stroke: color }}
                  aria-hidden="true"
                />
                <path
                  className="print-series mainprint"
                  data-series={series[0].configuration.model}
                  d={d}
                  style={{ stroke: color }}
                />
                <path
                  className="print-series-hit"
                  data-series={series[0].configuration.model}
                  d={d}
                  role="button"
                  tabIndex={0}
                  aria-label={
                    "Highlight " + series[0].configuration.model + " curve"
                  }
                  aria-pressed={pinned?.kind === "series" && pinned.id === key}
                  onMouseEnter={() => onHover(target)}
                  onMouseLeave={() => onHover(null)}
                  onFocus={() => onHover(target)}
                  onBlur={() => onHover(null)}
                  onClick={() => onPin(target)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onPin(target);
                    }
                  }}
                />
              </g>
            );
          })}
        {selectedPoint && (
          <path
            className="print-guide"
            d={
              "M" +
              left +
              " " +
              selectedPoint.y +
              " H" +
              selectedPoint.x +
              " V" +
              bottom
            }
            style={{ stroke: selectedPoint.color }}
            aria-hidden="true"
          />
        )}
        {points.map((p) => {
          const target = { kind: "point" as const, id: p.configuration.id };
          return (
            <g
              className={
                "print-point" +
                (selected === p.configuration.id ? " is-active" : "")
              }
              key={p.configuration.id}
              data-series-group={p.group}
              data-muted={muted(p.group)}
              data-config={p.configuration.id}
              data-value={p.value}
              data-percent={p.score}
              data-x={p.x}
              data-y={p.y}
              role="button"
              tabIndex={0}
              aria-pressed={
                pinned?.kind === "point" && pinned.id === p.configuration.id
              }
              aria-label={
                p.configuration.model +
                ", " +
                p.configuration.effort +
                ": " +
                p.score.toFixed(1) +
                "% Pass Average, " +
                format(p.value, axis, true) +
                " " +
                axisLabels[axis].toLowerCase() +
                " per run"
              }
              onMouseEnter={() => onHover(target)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(target)}
              onBlur={() => onHover(null)}
              onClick={() => onPin(target)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onPin(target);
                }
              }}
              style={{ color: curveColor(p.group, p.color) }}
            >
              <circle cx={p.x} cy={p.y} r={14} className="print-hit" />
              <circle cx={p.x} cy={p.y} r={10} className="print-focus" />
              {p.configuration.model === "gpt-5.6-sol" ? (
                <rect
                  x={p.x - 3.5}
                  y={p.y - 3.5}
                  width={7}
                  height={7}
                  className="print-mark"
                />
              ) : (
                <circle cx={p.x} cy={p.y} r={3.5} className="print-mark" />
              )}
            </g>
          );
        })}
        <g className="print-labels" aria-hidden="true">
          {labels.map((label) => (
            <g
              key={label.kind + label.point.configuration.id}
              className={"print-label label-" + label.kind}
              data-series-group={label.point.group}
              data-muted={muted(label.point.group)}
              style={{
                fill: muted(label.point.group)
                  ? "var(--plot-muted-label)"
                  : label.point.color,
              }}
            >
              <text x={label.x} y={label.y + 14} className="print-label-name">
                {label.title}
              </text>
              {label.detail && (
                <text
                  x={label.x}
                  y={label.y + 31}
                  className="print-label-value"
                >
                  {label.detail}
                </text>
              )}
            </g>
          ))}
        </g>
        <text
          className="print-axis-title"
          x={size.width / 2}
          y={size.height - 5}
          textAnchor="middle"
        >
          {axisTitles[axis]}
        </text>
      </svg>
    </div>
  );
}
