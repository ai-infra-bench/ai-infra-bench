export type AxisMetric =
  | "averageCostUsd"
  | "averageOutputTokens"
  | "averageToolCalls";

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
export type LabelKind = "series" | "model" | "effort";
export type LabelSize = {
  width: number;
  height: number;
  titleX: number;
  titleY: number;
  detailX: number;
  detailY: number;
};
export type LabelOptions = {
  sizes?: Readonly<Record<string, LabelSize>>;
  curves?: readonly {
    group: string;
    points: readonly { x: number; y: number }[];
  }[];
};
export function labelSizeKey(
  kind: LabelKind,
  title: string,
  detail: string | null,
) {
  return JSON.stringify([kind, title, detail]);
}
export type PlotLabel = Box & {
  point: PlotPoint;
  kind: LabelKind;
  title: string;
  detail: string | null;
  titleX: number;
  titleY: number;
  detailX: number;
  detailY: number;
  leader?: { x1: number; y1: number; x2: number; y2: number };
};

export const effortOrder = [
  "none",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
];

// Data colours are independent of the website theme. Add each published model
// here with an explicit, distinct colour; never assign colours by row order.
export const MODEL_COLORS: Readonly<Record<string, string>> = Object.freeze({
  "gpt-6-astra": "#3d657c",
  "gpt-5.6-sol": "#a16454",
});

export function modelColor(model: string) {
  if (Object.hasOwn(MODEL_COLORS, model)) return MODEL_COLORS[model];
  // Preserve a stable fallback for unregistered models until a colour is chosen.
  let hash = 0;
  for (const character of model)
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return ["#284b63", "#607784", "#7c4945", "#96675e", "#586c86"][hash % 5];
}

export function xDomain(maximum: number) {
  const rough = Math.max(maximum, 0.01) / 5;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const normalized = rough / magnitude;
  const step =
    (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) *
    magnitude;
  const max = Math.ceil((maximum * 1.08) / step) * step || step;
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, index) =>
    Number((index * step).toPrecision(10)),
  );
  return { max, ticks };
}

export function yDomain(scores: number[]) {
  if (scores.length === 0)
    return { min: 0, max: 100, ticks: [0, 20, 40, 60, 80, 100] };
  const min = Math.max(0, Math.floor((Math.min(...scores) - 5) / 5) * 5);
  const max = Math.min(100, Math.ceil((Math.max(...scores) + 5) / 5) * 5);
  const step = max - min > 40 ? 10 : 5;
  const ticks = Array.from(
    { length: Math.floor((max - min) / step) + 1 },
    (_, index) => min + index * step,
  );
  if (ticks.at(-1) !== max) ticks.push(max);
  return { min, max, ticks };
}

function overlap(a: Box, b: Box) {
  return (
    Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) *
    Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))
  );
}

// Move annotations, never data. Real SVG text metrics and sampled curve paths
// are supplied by the renderer; deterministic fallbacks support SSR and tests.
export function placePlotLabels(
  points: PlotPoint[],
  bounds: Box,
  compact: boolean,
  highlightedPointId: string | null = null,
  options: LabelOptions = {},
): PlotLabel[] {
  const labels: PlotLabel[] = [];
  const obstacles = points.map((point) => ({
    x: point.x - 7,
    y: point.y - 7,
    width: 14,
    height: 14,
  }));
  const groups = new Map<string, PlotPoint[]>();
  for (const point of points)
    groups.set(point.group, [...(groups.get(point.group) ?? []), point]);
  const paths = new Map<string, readonly { x: number; y: number }[]>();
  const lineSamples: Box[] = [];
  for (const [key, group] of groups) {
    group.sort(
      (a, b) =>
        effortOrder.indexOf(a.configuration.effort) -
        effortOrder.indexOf(b.configuration.effort),
    );
    const path =
      options.curves?.find((curve) => curve.group === key)?.points ?? group;
    paths.set(key, path);
    for (let index = 1; index < path.length; index++) {
      const a = path[index - 1];
      const b = path[index];
      const samples = Math.max(
        1,
        Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 8),
      );
      for (let sample = 0; sample <= samples; sample++) {
        lineSamples.push({
          x: a.x + ((b.x - a.x) * sample) / samples - 2,
          y: a.y + ((b.y - a.y) * sample) / samples - 2,
          width: 4,
          height: 4,
        });
      }
    }
  }
  const dimensions = (
    kind: LabelKind,
    title: string,
    detail: string | null,
  ): LabelSize => {
    const measured = options.sizes?.[labelSizeKey(kind, title, detail)];
    if (measured) return measured;
    const font = kind === "effort" ? (compact ? 15 : 16) : compact ? 17 : 19;
    return {
      width:
        Math.max(title.length * font * 0.53, (detail?.length ?? 0) * 6.6) + 4,
      height: detail ? 36 : 24,
      titleX: 2,
      titleY: 18,
      detailX: 2,
      detailY: 32,
    };
  };
  const distanceToBox = (point: { x: number; y: number }, box: Box) =>
    Math.hypot(
      Math.max(box.x - point.x, 0, point.x - box.x - box.width),
      Math.max(box.y - point.y, 0, point.y - box.y - box.height),
    );
  const connector = (
    anchor: { x: number; y: number },
    box: Box,
    startGap = 0,
  ): PlotLabel["leader"] => {
    const edge = {
      x: Math.max(box.x, Math.min(anchor.x, box.x + box.width)),
      y: Math.max(box.y, Math.min(anchor.y, box.y + box.height)),
    };
    const dx = edge.x - anchor.x,
      dy = edge.y - anchor.y,
      length = Math.hypot(dx, dy);
    if (length <= startGap + 3) return undefined;
    return {
      x1: anchor.x + (dx / length) * startGap,
      y1: anchor.y + (dy / length) * startGap,
      x2: edge.x - (dx / length) * 3,
      y2: edge.y - (dy / length) * 3,
    };
  };
  const crossesBox = (line: NonNullable<PlotLabel["leader"]>, box: Box) => {
    const count = Math.max(
      1,
      Math.ceil(Math.hypot(line.x2 - line.x1, line.y2 - line.y1) / 2),
    );
    for (let i = 0; i <= count; i++) {
      const x = line.x1 + ((line.x2 - line.x1) * i) / count,
        y = line.y1 + ((line.y2 - line.y1) * i) / count;
      if (
        x >= box.x - 3 &&
        x <= box.x + box.width + 3 &&
        y >= box.y - 3 &&
        y <= box.y + box.height + 3
      )
        return true;
    }
    return false;
  };
  const seriesConnector = (box: Box, key: string) => {
    const path = paths.get(key) ?? [];
    const ownDistance = Math.min(...path.map((p) => distanceToBox(p, box)));
    const otherDistance = Math.min(
      ...[...paths]
        .filter(([group]) => group !== key)
        .flatMap(([, curve]) => curve.map((p) => distanceToBox(p, box))),
    );
    if (ownDistance <= 24 && otherDistance >= ownDistance + 5)
      return { line: undefined, blocked: false };
    const awayFromKnots = path.filter(
      (p) =>
        !(groups.get(key) ?? []).some(
          (knot) => Math.hypot(knot.x - p.x, knot.y - p.y) < 8,
        ),
    );
    const anchors = [...(awayFromKnots.length ? awayFromKnots : path)].sort(
      (a, b) => distanceToBox(a, box) - distanceToBox(b, box),
    );
    for (const anchor of anchors) {
      if (distanceToBox(anchor, box) > ownDistance + 60) break;
      const line = connector(anchor, box);
      if (line && !labels.some((label) => crossesBox(line, label)))
        return { line, blocked: false };
    }
    return { line: undefined, blocked: true };
  };
  const choosePosition = (
    candidates: (Box & { preference: number })[],
    owner?: PlotPoint,
    seriesGroup?: string,
  ) => {
    let best: Box | null = null;
    let bestScore = Infinity;
    for (const candidate of candidates) {
      const box = {
        x: Math.max(
          bounds.x,
          Math.min(candidate.x, bounds.x + bounds.width - candidate.width),
        ),
        y: Math.max(
          bounds.y,
          Math.min(candidate.y, bounds.y + bounds.height - candidate.height),
        ),
        width: candidate.width,
        height: candidate.height,
      };
      const ownDistance = owner ? distanceToBox(owner, box) : 0;
      const competingDistance = owner
        ? Math.min(
            ...points
              .filter((point) => point.group === owner.group && point !== owner)
              .map((point) => distanceToBox(point, box)),
          )
        : Infinity;
      const ownCurveDistance = seriesGroup
        ? Math.min(
            ...(paths.get(seriesGroup) ?? []).map((p) => distanceToBox(p, box)),
          )
        : 0;
      const otherCurveDistance = seriesGroup
        ? Math.min(
            ...[...paths]
              .filter(([key]) => key !== seriesGroup)
              .flatMap(([, path]) => path.map((p) => distanceToBox(p, box))),
          )
        : Infinity;
      const connection = seriesGroup ? seriesConnector(box, seriesGroup) : null;
      const pointConnection =
        owner && (ownDistance > 25 || competingDistance < ownDistance + 3)
          ? connector(owner, box, 6)
          : undefined;
      const score =
        (labels.some(
          (label) =>
            overlap(box, {
              x: label.x - 3,
              y: label.y - 3,
              width: label.width + 6,
              height: label.height + 6,
            }) > 0,
        )
          ? 1000000
          : 0) +
        labels.reduce(
          (sum, label) =>
            sum +
            overlap(box, {
              x: label.x - 4,
              y: label.y - 4,
              width: label.width + 8,
              height: label.height + 8,
            }) *
              200,
          0,
        ) +
        obstacles.reduce(
          (sum, obstacle) => sum + overlap(box, obstacle) * 350,
          0,
        ) +
        lineSamples.reduce(
          (sum, sample) => sum + overlap(box, sample) * 18,
          0,
        ) +
        Math.hypot(candidate.x - box.x, candidate.y - box.y) * 5 +
        ownDistance ** 2 * 0.7 +
        Math.max(0, ownDistance + 7 - competingDistance) * 80 +
        (seriesGroup && Math.min(ownCurveDistance, otherCurveDistance) < 3
          ? 1000000
          : 0) +
        ownCurveDistance ** 2 * 2 +
        Math.max(0, ownCurveDistance + 6 - otherCurveDistance) * 220 +
        (connection?.blocked ? 1000000 : 0) +
        (pointConnection &&
        labels.some((label) => crossesBox(pointConnection, label))
          ? 1000000
          : 0) +
        (labels.some((label) => label.leader && crossesBox(label.leader, box))
          ? 1000000
          : 0) +
        candidate.preference;
      if (score < bestScore) {
        best = box;
        bestScore = score;
      }
    }
    return best;
  };

  const placeSeriesNames = () => {
    for (const [key, group] of groups) {
      if (group.length < 2) continue;
      const point = group[0];
      const title = point.configuration.model;
      const size = dimensions("series", title, null),
        { width, height } = size;
      const path = paths.get(key)!;
      const segments = path
        .slice(1)
        .map((end, index) => ({
          start: path[index],
          end,
          length: Math.hypot(end.x - path[index].x, end.y - path[index].y),
        }))
        .filter((segment) => segment.length > 0);
      const totalLength = segments.reduce(
        (sum, segment) => sum + segment.length,
        0,
      );
      const candidates: (Box & { preference: number })[] = [];
      for (const fraction of [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9]) {
        let travelled = 0;
        const segment = segments.find((segment) => {
          if (travelled + segment.length >= totalLength * fraction) return true;
          travelled += segment.length;
          return false;
        });
        if (!segment) continue;
        const t = (totalLength * fraction - travelled) / segment.length;
        let nx = -(segment.end.y - segment.start.y) / segment.length;
        let ny = (segment.end.x - segment.start.x) / segment.length;
        if (ny > 0) {
          nx = -nx;
          ny = -ny;
        }
        const x = segment.start.x + (segment.end.x - segment.start.x) * t;
        const y = segment.start.y + (segment.end.y - segment.start.y) * t;
        for (const side of [1, -1]) {
          for (const gap of [9, 16, 24]) {
            // Project the text box onto the segment normal so even steep
            // lines stay clear of the lettering without a background mask.
            const offset =
              (Math.abs(nx) * width) / 2 + (Math.abs(ny) * height) / 2 + gap;
            candidates.push({
              x: x + nx * offset * side - width / 2,
              y: y + ny * offset * side - height / 2,
              width,
              height,
              preference:
                Math.abs(fraction - 0.5) * 40 +
                gap * 0.5 +
                (side === 1 ? 0 : 1),
            });
          }
        }
      }
      // A small fallback grid handles narrow viewports where clamping a long
      // name would otherwise put its box directly across a curve.
      const gridX = compact
        ? Array.from(
            {
              length: Math.max(1, Math.floor((bounds.width - width) / 12) + 1),
            },
            (_, i) => bounds.x + i * 12,
          )
        : [
            bounds.x,
            bounds.x + (bounds.width - width) / 2,
            bounds.x + bounds.width - width,
          ];
      for (const x of gridX) {
        for (
          let y = bounds.y;
          y <= bounds.y + bounds.height - height;
          y += compact ? 12 : 16
        )
          candidates.push({ x, y, width, height, preference: 200 });
      }
      const best = choosePosition(candidates, undefined, key);
      if (best) {
        const leader = seriesConnector(best, key).line;
        labels.push({
          ...size,
          ...best,
          point,
          kind: "series",
          title,
          detail: null,
          leader,
        });
      }
    }
  };

  const standalone = (point: PlotPoint) =>
    groups.get(point.group)?.length === 1;
  const showPointLabels = groups.size <= 3;
  // In dense mode names stay stationary when one point's detail is revealed.
  if (!showPointLabels) placeSeriesNames();
  const ordered = [...points].sort(
    (a, b) =>
      Number(standalone(b)) - Number(standalone(a)) || b.score - a.score,
  );
  for (const point of ordered) {
    const isStandalone = standalone(point);
    const showDetails =
      showPointLabels || point.configuration.id === highlightedPointId;
    if (!showDetails && !isStandalone) continue;
    const title = isStandalone
      ? point.configuration.model
      : point.configuration.effort;
    const detail = showDetails
      ? isStandalone
        ? `${point.configuration.effort} · ${point.score.toFixed(1)}%`
        : `${point.score.toFixed(1)}%`
      : null;
    const kind = isStandalone ? "model" : "effort";
    const size = dimensions(kind, title, detail),
      { width, height } = size;
    const positions = [
      [10, -height - 9],
      [-width - 10, -height - 9],
      [10, 10],
      [-width - 10, 10],
      [-width / 2, -height - 12],
      [-width / 2, 12],
      [13, -height / 2],
      [-width - 13, -height / 2],
      [10, -height - 30],
      [-width - 10, -height - 30],
      [10, 30],
      [-width - 10, 30],
    ];
    const best = choosePosition(
      positions.map(([dx, dy]) => ({
        x: point.x + dx,
        y: point.y + dy,
        width,
        height,
        preference: Math.abs(dx + width / 2) * 0.05,
      })),
      point,
    );
    if (best) {
      const distance = distanceToBox(point, best);
      const ambiguous = points.some(
        (other) =>
          other !== point &&
          other.group === point.group &&
          distanceToBox(other, best) < distance + 3,
      );
      let leader: PlotLabel["leader"];
      if (!isStandalone && (distance > 25 || ambiguous)) {
        const edge = {
          x: Math.max(best.x, Math.min(point.x, best.x + width)),
          y: Math.max(best.y, Math.min(point.y, best.y + height)),
        };
        const dx = edge.x - point.x,
          dy = edge.y - point.y,
          length = Math.hypot(dx, dy);
        if (length > 9)
          leader = {
            x1: point.x + (dx / length) * 6,
            y1: point.y + (dy / length) * 6,
            x2: edge.x - (dx / length) * 3,
            y2: edge.y - (dy / length) * 3,
          };
      }
      labels.push({ ...size, ...best, point, kind, title, detail, leader });
    }
  }
  if (showPointLabels) placeSeriesNames();
  return labels;
}
