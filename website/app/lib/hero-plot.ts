export type HeroAxis = "cost" | "tokens" | "tools" | "effort";
export type HeroScore = "passAverage" | "passAtK";
export type NumericDomain = { min: number; max: number; ticks: number[] };

export function focusedDomain(values: number[]): NumericDomain {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return { min: 0, max: 1, ticks: [0, 0.5, 1] };
  const lo = Math.min(...finite),
    hi = Math.max(...finite);
  const span = hi - lo || Math.max(Math.abs(hi) * 0.4, 1);
  const rough = span / 4;
  const unit = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].find((n) => n * unit >= rough)! * unit;
  let min = Math.max(0, Math.floor(lo / step) * step);
  let max = Math.ceil(hi / step) * step;
  if (min === max) {
    min = Math.max(0, min - step);
    max += step;
  }
  const ticks = Array.from(
    { length: Math.round((max - min) / step) + 1 },
    (_, i) => Number((min + i * step).toPrecision(12)),
  );
  return { min, max, ticks };
}
export function percentDomain(
  values: number[],
  deviations: number[] = [],
): NumericDomain {
  if (!values.length) return { min: 0, max: 100, ticks: [0, 25, 50, 75, 100] };
  const low = Math.min(...values.map((v, i) => v - (deviations[i] ?? 0)));
  const high = Math.max(...values.map((v, i) => v + (deviations[i] ?? 0)));
  const min = Math.max(0, Math.floor((low - 2) / 5) * 5);
  const max = Math.min(100, Math.ceil((high + 2) / 5) * 5);
  const step = max - min > 45 ? 10 : 5;
  const ticks = Array.from(
    { length: Math.floor((max - min) / step) + 1 },
    (_, i) => min + i * step,
  );
  if (ticks.at(-1) !== max) ticks.push(max);
  return { min, max, ticks };
}
export function project(
  value: number,
  domain: NumericDomain,
  start: number,
  length: number,
) {
  return start + ((value - domain.min) / (domain.max - domain.min)) * length;
}
