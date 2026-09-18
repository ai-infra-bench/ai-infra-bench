export type PlotTarget = { kind: "point" | "series"; id: string } | null;
type Identity = {
  id: string;
  model: string;
  agent: string;
  agentVersion: string;
};

export function plotGroupKey(configuration: Omit<Identity, "id">) {
  return (
    configuration.model +
    "::" +
    configuration.agent +
    "::" +
    configuration.agentVersion
  );
}

// Hover/focus temporarily overrides a pinned selection. A series has no point
// readout or projection guides; moving onto a point keeps that series focused.
export function resolvePlotFocus(
  configurations: readonly Identity[],
  hover: PlotTarget,
  pinned: PlotTarget,
) {
  const target = hover ?? pinned;
  if (target?.kind === "series") {
    const configuration = configurations.find(
      (item) => plotGroupKey(item) === target.id,
    );
    return { pointId: null, group: configuration ? target.id : null };
  }
  const point =
    target?.kind === "point"
      ? configurations.find((item) => item.id === target.id)
      : undefined;
  return {
    pointId: point?.id ?? null,
    group: point ? plotGroupKey(point) : null,
  };
}
