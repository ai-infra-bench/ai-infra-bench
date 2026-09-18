type HitPoint = { x: number; y: number; configuration: { id: string } };

/** Hit testing follows geometry, not SVG paint order. Keyboard activation
 * continues to target the focused element, including coincident points. */
export function nearestPlotPoint<T extends HitPoint>(
  points: readonly T[],
  pointer: { x: number; y: number },
  radius = 24,
): T | null {
  let nearest: T | null = null;
  let distance = radius * radius;
  for (const point of points) {
    const candidate = (point.x - pointer.x) ** 2 + (point.y - pointer.y) ** 2;
    if (
      candidate < distance ||
      (candidate === distance &&
        (!nearest || point.configuration.id < nearest.configuration.id))
    ) {
      nearest = point;
      distance = candidate;
    }
  }
  return nearest;
}
