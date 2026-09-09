export type AxisMetric = 'averageCostUsd' | 'averageOutputTokens' | 'averageToolCalls';

export type ChartConfiguration = {
  id: string;
  model: string;
  effort: string;
  agent: string;
  agentVersion: string;
  metrics: {
    passAverage: number | null;
    averageCostUsd: number | null;
    averageOutputTokens: number | null;
    averageToolCalls: number | null;
  };
};

export type PlotPoint = {
  configuration: ChartConfiguration;
  x: number;
  y: number;
  value: number;
  score: number;
  color: string;
  group: string;
};

type Box = { x: number; y: number; width: number; height: number };
export type PlotLabel = Box & {
  point: PlotPoint;
  kind: 'series' | 'model' | 'effort';
  title: string;
  detail: string | null;
};

export const effortOrder = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];

// Data colours are independent of the website theme. Add each published model
// here with an explicit, distinct colour; never assign colours by row order.
export const MODEL_COLORS: Readonly<Record<string, string>> = Object.freeze({
  'gpt-6-astra': '#3d657c',
  'gpt-5.6-sol': '#a16454',
});

export function modelColor(model: string) {
  if (Object.hasOwn(MODEL_COLORS, model)) return MODEL_COLORS[model];
  // Preserve a stable fallback for unregistered models until a colour is chosen.
  let hash = 0;
  for (const character of model) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return ['#284b63', '#607784', '#7c4945', '#96675e', '#586c86'][hash % 5];
}

export function xDomain(maximum: number) {
  const rough = Math.max(maximum, 0.01) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude;
  const max = Math.ceil((maximum * 1.08) / step) * step || step;
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, index) => Number((index * step).toPrecision(10)));
  return { max, ticks };
}

export function yDomain(scores: number[]) {
  if (scores.length === 0) return { min: 0, max: 100, ticks: [0, 20, 40, 60, 80, 100] };
  const min = Math.max(0, Math.floor((Math.min(...scores) - 5) / 5) * 5);
  const max = Math.min(100, Math.ceil((Math.max(...scores) + 5) / 5) * 5);
  const step = max - min > 40 ? 10 : 5;
  const ticks = Array.from({ length: Math.floor((max - min) / step) + 1 }, (_, index) => min + index * step);
  if (ticks.at(-1) !== max) ticks.push(max);
  return { min, max, ticks };
}

function overlap(a: Box, b: Box) {
  return Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x))
    * Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
}

// Move annotations, never data. Score candidate positions against labels,
// point marks, and the actual line segments to keep the drawing legible.
export function placePlotLabels(points: PlotPoint[], bounds: Box, compact: boolean, highlightedPointId: string | null = null): PlotLabel[] {
  const labels: PlotLabel[] = [];
  const obstacles = points.map((point) => ({ x: point.x - 10, y: point.y - 10, width: 20, height: 20 }));
  const groups = new Map<string, PlotPoint[]>();
  for (const point of points) groups.set(point.group, [...(groups.get(point.group) ?? []), point]);
  const lineSamples: Box[] = [];
  for (const group of groups.values()) {
    group.sort((a, b) => effortOrder.indexOf(a.configuration.effort) - effortOrder.indexOf(b.configuration.effort));
    for (let index = 1; index < group.length; index++) {
      const a = group[index - 1];
      const b = group[index];
      const samples = Math.max(1, Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 8));
      for (let sample = 0; sample <= samples; sample++) {
        lineSamples.push({ x: a.x + (b.x - a.x) * sample / samples - 2, y: a.y + (b.y - a.y) * sample / samples - 2, width: 4, height: 4 });
      }
    }
  }

  const choosePosition = (candidates: (Box & { preference: number })[]) => {
    let best: Box | null = null;
    let bestScore = Infinity;
    for (const candidate of candidates) {
      const box = {
        x: Math.max(bounds.x, Math.min(candidate.x, bounds.x + bounds.width - candidate.width)),
        y: Math.max(bounds.y, Math.min(candidate.y, bounds.y + bounds.height - candidate.height)),
        width: candidate.width,
        height: candidate.height,
      };
      const score = labels.reduce((sum, label) => sum + overlap(box, { x: label.x - 5, y: label.y - 5, width: label.width + 10, height: label.height + 10 }) * 100, 0)
        + obstacles.reduce((sum, obstacle) => sum + overlap(box, obstacle) * 200, 0)
        + lineSamples.reduce((sum, sample) => sum + overlap(box, sample) * 4, 0)
        + Math.hypot(candidate.x - box.x, candidate.y - box.y) * 5
        + candidate.preference;
      if (score < bestScore) { best = box; bestScore = score; }
    }
    return best;
  };

  // Name the whole series beside a spacious segment, independently of the
  // effort labels. Reserve its space before placing the point annotations.
  for (const group of groups.values()) {
    if (group.length < 2) continue;
    const point = group[0];
    const title = point.configuration.model;
    const width = title.length * (compact ? 16 : 17) * 0.52 + 4;
    const height = 22;
    const segments = group.slice(1).map((end, index) => ({
      start: group[index], end,
      length: Math.hypot(end.x - group[index].x, end.y - group[index].y),
    })).filter((segment) => segment.length > 0);
    const longest = Math.max(...segments.map((segment) => segment.length), 1);
    const candidates: (Box & { preference: number })[] = [];
    for (const segment of segments) {
      let nx = -(segment.end.y - segment.start.y) / segment.length;
      let ny = (segment.end.x - segment.start.x) / segment.length;
      if (ny > 0) { nx = -nx; ny = -ny; }
      for (const fraction of [0.5, 0.4, 0.6]) {
        const x = segment.start.x + (segment.end.x - segment.start.x) * fraction;
        const y = segment.start.y + (segment.end.y - segment.start.y) * fraction;
        for (const side of [1, -1]) {
          for (const gap of [9, 16, 24]) {
            // Project the text box onto the segment normal so even steep
            // lines stay clear of the lettering without a background mask.
            const offset = Math.abs(nx) * width / 2 + Math.abs(ny) * height / 2 + gap;
            candidates.push({
              x: x + nx * offset * side - width / 2,
              y: y + ny * offset * side - height / 2,
              width, height,
              preference: (1 - segment.length / longest) * 20
                + Math.abs(fraction - 0.5) * 8 + gap * 0.05 + (side === 1 ? 0 : 0.5),
            });
          }
        }
      }
    }
    const best = choosePosition(candidates);
    if (best) labels.push({ ...best, point, kind: 'series', title, detail: null });
  }

  const standalone = (point: PlotPoint) => groups.get(point.group)?.length === 1;
  const showPointLabels = groups.size <= 3;
  const ordered = [...points].sort((a, b) => Number(standalone(b)) - Number(standalone(a)) || b.score - a.score);
  for (const point of ordered) {
    const isStandalone = standalone(point);
    const showDetails = showPointLabels || point.configuration.id === highlightedPointId;
    if (!showDetails && !isStandalone) continue;
    const title = isStandalone ? point.configuration.model : point.configuration.effort;
    const detail = showDetails
      ? (isStandalone ? `${point.configuration.effort} · ${point.score.toFixed(1)}%` : `${point.score.toFixed(1)}%`)
      : null;
    const fontSize = isStandalone ? (compact ? 16 : 17) : 14;
    const width = Math.max(title.length * fontSize * 0.52, (detail?.length ?? 0) * 6.4) + 4;
    const height = detail ? 33 : 22;
    const positions = [
      [14, -height - 10], [-width - 14, -height - 10],
      [14, 12], [-width - 14, 12],
      [-width / 2, -height - 16], [-width / 2, 17],
      [20, -height / 2], [-width - 20, -height / 2],
      [14, -height - 34], [-width - 14, -height - 34],
      [14, 34], [-width - 14, 34],
    ];
    const best = choosePosition(positions.map(([dx, dy]) => ({
      x: point.x + dx, y: point.y + dy, width, height,
      preference: Math.hypot(dx, dy) * 0.02,
    })));
    if (best) labels.push({ ...best, point, kind: isStandalone ? 'model' : 'effort', title, detail });
  }
  return labels;
}
