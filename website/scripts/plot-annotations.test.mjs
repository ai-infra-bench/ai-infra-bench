import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  placePlotLabels,
  labelSizeKey,
  effortOrder,
} from "../app/lib/leaderboard-chart.ts";
import { sampleCurve, descendingLinear } from "../app/lib/print-geometry.ts";
import { focusedDomain } from "../app/lib/hero-plot.ts";
const data = JSON.parse(
  await readFile(
    new URL("../app/generated/leaderboard.json", import.meta.url),
    "utf8",
  ),
).configurations;
const distance = (p, b) =>
  Math.hypot(
    Math.max(b.x - p.x, 0, p.x - b.x - b.width),
    Math.max(b.y - p.y, 0, p.y - b.y - b.height),
  );
test("annotation sampling follows the cubic path and keeps measured knots", () => {
  const p = [
    { x: 0, y: 0 },
    { x: 60, y: 60 },
    { x: 120, y: 30 },
  ];
  const curve = sampleCurve(p, 4);
  assert.deepEqual(curve[0], p[0]);
  assert.deepEqual(curve.at(-1), p.at(-1));
  assert.ok(curve.some((q) => q.x === 60 && q.y === 60));
  assert.ok(curve.some((q) => q.x > 0 && q.x < 60 && Math.abs(q.y - q.x) > 2));
  assert.ok(
    curve
      .slice(1)
      .every((q, i) => Math.hypot(q.x - curve[i].x, q.y - curve[i].y) <= 4.001),
  );
});
test("mobile labels that cannot stay nearest to their owner receive explicit leaders", () => {
  for (const metric of [
    "averageCostUsd",
    "averageOutputTokens",
    "averageToolCalls",
  ]) {
    const xd = focusedDomain(data.map((c) => c.metrics[metric]));
    const points = [...data]
      .sort(
        (a, b) => effortOrder.indexOf(a.effort) - effortOrder.indexOf(b.effort),
      )
      .map((c) => ({
        configuration: c,
        group: c.model,
        color: "#000",
        value: c.metrics[metric],
        score: c.metrics.passAverage,
        x: descendingLinear(c.metrics[metric], xd.min, xd.max, 40, 212),
        y: 346 - ((c.metrics.passAverage - 30) / 40) * 312,
      }));
    const curves = [...new Set(points.map((p) => p.group))].map((group) => ({
      group,
      points: sampleCurve(points.filter((p) => p.group === group)),
    }));
    const labels = placePlotLabels(
      points,
      { x: 44, y: 38, width: 204, height: 304 },
      true,
      null,
      { curves },
    );
    assert.equal(labels.length, 10);
    for (const label of labels.filter((l) => l.kind === "effort")) {
      const d = distance(label.point, label);
      if (
        points.some(
          (p) =>
            p !== label.point &&
            p.group === label.point.group &&
            distance(p, label) < d,
        )
      )
        assert.ok(label.leader);
    }
  }
});
test("real text dimensions are honoured rather than replaced by guessed character widths", () => {
  const c = data[0],
    p = {
      configuration: c,
      group: c.model,
      color: "#000",
      value: 1,
      score: c.metrics.passAverage,
      x: 160,
      y: 140,
    };
  const title = c.model,
    detail = c.effort + " · " + p.score.toFixed(1) + "%";
  const size = {
    width: 173,
    height: 41,
    titleX: 3,
    titleY: 19,
    detailX: 2,
    detailY: 36,
  };
  const [label] = placePlotLabels(
    [p],
    { x: 10, y: 10, width: 500, height: 300 },
    false,
    null,
    { sizes: { [labelSizeKey("model", title, detail)]: size } },
  );
  assert.equal(label.width, 173);
  assert.equal(label.height, 41);
  assert.equal(label.titleY, 19);
});
