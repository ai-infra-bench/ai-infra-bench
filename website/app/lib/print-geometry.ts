export type XY = { x: number; y: number };
export function linear(
  value: number,
  min: number,
  max: number,
  start: number,
  length: number,
) {
  return start + ((value - min) / (max - min)) * length;
}
// A real reversed scale, shared by ticks, measurements and their connecting path.
export function descendingLinear(
  value: number,
  min: number,
  max: number,
  start: number,
  length: number,
) {
  return start + ((max - value) / (max - min)) * length;
}
// Shape-preserving Hermite interpolation. Knots are measurements; connecting
// segments guide the eye and are not estimates of unmeasured configurations.
export function curveSegments(points: XY[]) {
  if (points.length < 2) return [];
  const slopes = points
    .slice(1)
    .map((p, i) => (p.y - points[i].y) / (p.x - points[i].x));
  const tangents = points.map((_, i) =>
    i === 0
      ? slopes[0]
      : i === points.length - 1
        ? slopes.at(-1)!
        : slopes[i - 1] * slopes[i] <= 0
          ? 0
          : 2 / (1 / slopes[i - 1] + 1 / slopes[i]),
  );
  for (let i = 0; i < slopes.length; i++) {
    if (slopes[i] === 0) {
      tangents[i] = 0;
      tangents[i + 1] = 0;
      continue;
    }
    const a = tangents[i] / slopes[i],
      b = tangents[i + 1] / slopes[i],
      length = Math.hypot(a, b);
    if (length > 3) {
      tangents[i] = ((3 * a) / length) * slopes[i];
      tangents[i + 1] = ((3 * b) / length) * slopes[i];
    }
  }
  return points.slice(1).map((end, i) => {
    const start = points[i],
      dx = (end.x - start.x) / 3;
    return {
      start,
      c1: { x: start.x + dx, y: start.y + tangents[i] * dx },
      c2: { x: end.x - dx, y: end.y - tangents[i + 1] * dx },
      end,
    };
  });
}
export function curvePath(points: XY[]) {
  if (!points.length) return "";
  return (
    "M" +
    points[0].x +
    " " +
    points[0].y +
    curveSegments(points)
      .map(
        (s) =>
          " C" +
          s.c1.x +
          " " +
          s.c1.y +
          " " +
          s.c2.x +
          " " +
          s.c2.y +
          " " +
          s.end.x +
          " " +
          s.end.y,
      )
      .join("")
  );
}

/** Sample the same cubic geometry as curvePath for annotation avoidance.
 * This does not alter knots, control points or the rendered data path. */
export function sampleCurve(points: XY[], spacing = 6): XY[] {
  if (!points.length) return [];
  return [
    points[0],
    ...curveSegments(points).flatMap((segment) => {
      const { start: a, c1: b, c2: c, end: d } = segment;
      const length =
        Math.hypot(b.x - a.x, b.y - a.y) +
        Math.hypot(c.x - b.x, c.y - b.y) +
        Math.hypot(d.x - c.x, d.y - c.y);
    // Cubic speed is bounded by three times the control-polygon length.
    // Uniform t intervals therefore need this factor to bound physical gaps,
    // especially near steep end tangents on a small plot.
    const count = Math.max(2, Math.min(4096, Math.ceil(3 * length / spacing)));
      return Array.from({ length: count }, (_, index) => {
        const t = (index + 1) / count,
          u = 1 - t;
        return {
          x:
            u * u * u * a.x +
            3 * u * u * t * b.x +
            3 * u * t * t * c.x +
            t * t * t * d.x,
          y:
            u * u * u * a.y +
            3 * u * u * t * b.y +
            3 * u * t * t * c.y +
            t * t * t * d.y,
        };
      });
    }),
  ];
}
export function polarPoint(
  value: number,
  score: number,
  xMin: number,
  xMax: number,
  cx: number,
  cy: number,
  radius: number,
) {
  const angle = linear(value, xMin, xMax, -Math.PI * 0.86, Math.PI * 1.72);
  const r = linear(score, 0, 100, 0, radius);
  return { x: cx + Math.sin(angle) * r, y: cy - Math.cos(angle) * r, angle, r };
}

export function closedBand(upper: XY[], lower: XY[]) {
  const reversed = curveSegments(lower).reverse();
  if (!upper.length || !lower.length) return "";
  return (
    curvePath(upper) +
    " L" +
    lower.at(-1)!.x +
    " " +
    lower.at(-1)!.y +
    reversed
      .map(
        (s) =>
          " C" +
          s.c2.x +
          " " +
          s.c2.y +
          " " +
          s.c1.x +
          " " +
          s.c1.y +
          " " +
          s.start.x +
          " " +
          s.start.y,
      )
      .join("") +
    " Z"
  );
}
export function polarConnection(
  points: { value: number; score: number }[],
  min: number,
  max: number,
  cx: number,
  cy: number,
  radius: number,
) {
  const samples = points.flatMap((p, i) =>
    i === 0
      ? [polarPoint(p.value, p.score, min, max, cx, cy, radius)]
      : Array.from({ length: 32 }, (_, j) => {
          const t = (j + 1) / 32,
            previous = points[i - 1];
          return polarPoint(
            previous.value + (p.value - previous.value) * t,
            previous.score + (p.score - previous.score) * t,
            min,
            max,
            cx,
            cy,
            radius,
          );
        }),
  );
  return "M" + samples.map((p) => p.x + " " + p.y).join(" L");
}
