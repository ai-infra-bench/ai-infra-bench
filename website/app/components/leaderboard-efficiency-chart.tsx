'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { MouseEvent, PointerEvent } from 'react';
import {
  effortOrder, modelColor, placePlotLabels, xDomain, yDomain,
  type AxisMetric, type ChartConfiguration, type PlotPoint,
} from '@/app/lib/leaderboard-chart';

const axisOptions: { key: AxisMetric; label: string; title: string }[] = [
  { key: 'averageCostUsd', label: 'Cost', title: 'Average cost per run (USD)' },
  { key: 'averageOutputTokens', label: 'Output tokens', title: 'Average output tokens per run' },
  { key: 'averageToolCalls', label: 'Tool calls', title: 'Average tool calls per run' },
];

function formatValue(value: number, metric: AxisMetric, exact = false) {
  if (metric === 'averageCostUsd') return '$' + value.toFixed(exact ? 2 : Number.isInteger(value) ? 0 : 1);
  if (metric === 'averageOutputTokens') return exact ? Math.round(value).toLocaleString('en-US') : Number((value / 1000).toFixed(1)) + 'k';
  return value.toFixed(exact ? 1 : 0);
}

export function LeaderboardEfficiencyChart({ configurations }: { configurations: ChartConfiguration[] }) {
  const [axisMetric, setAxisMetric] = useState<AxisMetric>('averageCostUsd');
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [pinnedId, setPinnedId] = useState<string | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [{ width, height }, setSize] = useState({ width: 1000, height: 528 });
  const frame = useRef<HTMLDivElement>(null);
  const id = useId();
  const compact = width < 600;
  const margin = { top: 28, right: compact ? 14 : 24, bottom: 58, left: compact ? 40 : 52 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const selectedAxis = axisOptions.find((axis) => axis.key === axisMetric)!;

  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    const update = () => {
      const { width: nextWidth, height: nextHeight } = element.getBoundingClientRect();
      setSize((current) => current.width === nextWidth && current.height === nextHeight
        ? current
        : { width: nextWidth, height: nextHeight });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const { points, horizontal, vertical, series } = useMemo(() => {
    const valid = configurations.filter((configuration) => {
      const value = configuration.metrics[axisMetric];
      const score = configuration.metrics.passAverage;
      return value !== null && Number.isFinite(value) && value >= 0
        && score !== null && Number.isFinite(score) && score >= 0 && score <= 100;
    });
    const horizontal = xDomain(Math.max(...valid.map((configuration) => configuration.metrics[axisMetric]!), 0));
    const vertical = yDomain(valid.map((configuration) => configuration.metrics.passAverage!));
    const points: PlotPoint[] = valid.map((configuration) => {
      const value = configuration.metrics[axisMetric]!;
      const score = configuration.metrics.passAverage!;
      return {
        configuration, value, score,
        x: margin.left + (1 - value / horizontal.max) * plotWidth,
        y: margin.top + (1 - (score - vertical.min) / (vertical.max - vertical.min)) * plotHeight,
        color: modelColor(configuration.model),
        group: configuration.model + '::' + configuration.agent + '::' + configuration.agentVersion,
      };
    });
    const groups = new Map<string, PlotPoint[]>();
    for (const point of points) groups.set(point.group, [...(groups.get(point.group) ?? []), point]);
    const series = [...groups.values()].map((group) => {
      group.sort((a, b) => effortOrder.indexOf(a.configuration.effort) - effortOrder.indexOf(b.configuration.effort));
      return group;
    });
    return { points, horizontal, vertical, series };
  }, [configurations, axisMetric, margin.left, margin.top, plotWidth, plotHeight]);

  const labels = useMemo(() => placePlotLabels(points, {
    x: margin.left + 6, y: margin.top + 4, width: plotWidth - 12, height: plotHeight - 8,
  }, compact), [points, margin.left, margin.top, plotWidth, plotHeight, compact]);
  const activeId = hoveredId ?? focusedId ?? pinnedId;
  const active = points.find((point) => point.configuration.id === activeId);
  const xPosition = (value: number) => margin.left + (1 - value / horizontal.max) * plotWidth;
  const yPosition = (score: number) => margin.top + (1 - (score - vertical.min) / (vertical.max - vertical.min)) * plotHeight;
  const bottom = margin.top + plotHeight;

  const closestPoint = (event: PointerEvent<SVGSVGElement> | MouseEvent<SVGSVGElement>) => {
    const target = event.target as Element;
    const labelId = target.closest('[data-label-for]')?.getAttribute('data-label-for');
    if (labelId) return labelId;
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) * width / box.width;
    const y = (event.clientY - box.top) * height / box.height;
    let closest: string | null = null;
    let distance = 24;
    for (const point of points) {
      const next = Math.hypot(point.x - x, point.y - y);
      if (next < distance) { closest = point.configuration.id; distance = next; }
    }
    return closest;
  };

  const reset = () => { setHoveredId(null); setPinnedId(null); setFocusedId(null); };
  const select = (pointId: string | null) => setPinnedId((current) => current === pointId ? null : pointId);

  return (
    <figure className="paper-figure" aria-label="Model performance and resource use" onKeyDown={(event) => {
      if (event.key === 'Escape') { reset(); event.stopPropagation(); }
    }}>
      <div className="figure-toolbar">
        <span className="figure-measure">Pass average <span>(%)</span></span>
        <div className="figure-axis-options" role="group" aria-label="Compare performance by">
          {axisOptions.map((axis) => (
            <button key={axis.key} type="button" aria-pressed={axisMetric === axis.key}
              onClick={() => { setAxisMetric(axis.key); setHoveredId(null); }}>
              {axis.label}
            </button>
          ))}
        </div>
      </div>

      <div className="paper-plot-frame" ref={frame}>
        {points.length === 0 ? <p className="plot-empty">No recorded results for this metric.</p> : (
          <svg className="paper-plot" viewBox={'0 0 ' + width + ' ' + height} role="group"
            aria-labelledby={id + '-title ' + id + '-description'}
            onPointerMove={(event) => { if (event.pointerType !== 'touch') setHoveredId(closestPoint(event)); }}
            onPointerLeave={() => setHoveredId(null)}
            onClick={(event) => { select(closestPoint(event)); setFocusedId(null); setHoveredId(null); }}>
            <title id={id + '-title'}>{'Pass average versus ' + selectedAxis.label.toLowerCase()}</title>
            <desc id={id + '-description'}>{'Lower resource use is to the right. The vertical axis shows ' + vertical.min + ' to ' + vertical.max + ' percent. Lines join effort levels within a model and harness. Select a point to keep its values visible. Press Escape to clear.'}</desc>

            <g className="plot-grid" aria-hidden="true">
              {vertical.ticks.map((tick) => (
                <line key={'y-' + tick} x1={margin.left} x2={width - margin.right} y1={yPosition(tick)} y2={yPosition(tick)} />
              ))}
            </g>
            <path className="plot-axis" d={'M' + margin.left + ' ' + margin.top + ' V' + bottom + ' H' + (width - margin.right)} aria-hidden="true" />

            <g className="plot-ticks" aria-hidden="true">
              {horizontal.ticks.filter((_, index) => !compact || index % 2 === 0 || index === horizontal.ticks.length - 1).map((tick) => (
                <g key={tick}>
                  <line className="plot-tick-mark" x1={xPosition(tick)} x2={xPosition(tick)} y1={bottom} y2={bottom + 5} />
                  <text x={xPosition(tick)} y={bottom + 23} textAnchor="middle">{formatValue(tick, axisMetric)}</text>
                </g>
              ))}
              {vertical.ticks.map((tick) => (
                <g key={tick}>
                  <line className="plot-tick-mark" x1={margin.left - 5} x2={margin.left} y1={yPosition(tick)} y2={yPosition(tick)} />
                  <text x={margin.left - 12} y={yPosition(tick) + 4} textAnchor="end">{tick}</text>
                </g>
              ))}
              <text className="plot-axis-title" x={margin.left + plotWidth / 2} y={height - 5} textAnchor="middle">{selectedAxis.title}</text>
            </g>

            {series.map((group) => group.length > 1 && (
              <polyline key={group[0].group} className="plot-series" points={group.map((point) => point.x + ',' + point.y).join(' ')}
                style={{ stroke: group[0].color, opacity: active && active.group !== group[0].group ? 0.25 : 1 }} />
            ))}

            {active && (
              <g className="plot-crosshair" style={{ color: active.color }} aria-hidden="true">
                <path d={'M' + margin.left + ' ' + active.y + ' H' + active.x + ' V' + bottom} />
                <circle cx={active.x} cy={active.y} r={10} />
              </g>
            )}

            {points.map((point) => (
              <g key={point.configuration.id} className="plot-point" role="button" tabIndex={0}
                data-point-id={point.configuration.id}
                aria-pressed={pinnedId === point.configuration.id}
                aria-label={point.configuration.model + ', ' + point.configuration.effort + ': ' + point.score.toFixed(1) + '% pass average, ' + formatValue(point.value, axisMetric, true) + ' ' + selectedAxis.label.toLowerCase() + ' per run'}
                style={{ color: point.color, opacity: active && active.group !== point.group ? 0.4 : 1 }}
                onFocus={() => setFocusedId(point.configuration.id)} onBlur={() => setFocusedId(null)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(point.configuration.id); }
                }}>
                <circle cx={point.x} cy={point.y} r={22} className="plot-hit" />
                <circle cx={point.x} cy={point.y} r={10} className="plot-focus-ring" />
                {point.configuration.model === 'gpt-5.6-sol'
                  ? <rect x={point.x - 3.5} y={point.y - 3.5} width={7} height={7} className="plot-mark" />
                  : <circle cx={point.x} cy={point.y} r={3.5} className="plot-mark" />}
              </g>
            ))}

            {labels.map((label) => (
              <g className={'plot-label' + (label.kind !== 'effort' ? ' is-model' : '') + (label.kind === 'series' ? ' is-series' : '')}
                key={label.kind === 'series' ? 'series-' + label.point.group : label.point.configuration.id}
                data-label-for={label.kind === 'series' ? undefined : label.point.configuration.id}
                style={{ color: label.point.color, opacity: active && active.group !== label.point.group ? 0.4 : 1 }} aria-hidden="true">
                <text x={label.x} y={label.y + 14} className="plot-label-title">{label.title}</text>
                {label.detail && <text x={label.x} y={label.y + 29} className="plot-label-detail">{label.detail}</text>}
              </g>
            ))}
          </svg>
        )}
      </div>

      <figcaption className="figure-footer">
        <div className="figure-readout" aria-live="polite" aria-atomic="true">
          {active && <>
            <span className="readout-identity" style={{ color: active.color }}>{active.configuration.model} <span>{active.configuration.effort}</span></span>
            <span>{active.score.toFixed(1)}% <span>pass avg</span></span>
            <span>{formatValue(active.value, axisMetric, true)} <span>/ run</span></span>
            {pinnedId && <button type="button" onClick={reset} aria-label="Clear selected configuration">Clear</button>}
          </>}
        </div>
      </figcaption>
    </figure>
  );
}
