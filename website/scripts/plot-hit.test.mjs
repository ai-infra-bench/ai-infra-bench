import test from "node:test";
import assert from "node:assert/strict";
import { nearestPlotPoint } from "../app/lib/plot-hit.ts";

const medium = { x: 100, y: 100, configuration: { id: "medium" } };
const high = { x: 105, y: 112, configuration: { id: "high" } };
test("overlapping touch areas select the nearest point regardless of paint order", () => {
  for (const points of [
    [medium, high],
    [high, medium],
  ]) {
    assert.equal(nearestPlotPoint(points, { x: 100, y: 100 }, 24), medium);
    assert.equal(nearestPlotPoint(points, { x: 105, y: 112 }, 24), high);
    assert.equal(nearestPlotPoint(points, { x: 100, y: 98 }, 24), medium);
  }
});
test("empty space does not select a point, and equal-distance ties are stable", () => {
  assert.equal(nearestPlotPoint([medium, high], { x: 200, y: 200 }, 24), null);
  assert.equal(nearestPlotPoint([], { x: 0, y: 0 }), null);
  const a = { ...medium, configuration: { id: "a" } },
    b = { ...medium, configuration: { id: "b" } };
  assert.equal(nearestPlotPoint([b, a], a), a);
  assert.equal(nearestPlotPoint([a, b], a), a);
});
