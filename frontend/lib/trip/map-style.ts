import type { ExpressionSpecification } from "mapbox-gl";

type ActiveAwareLineWidthStop = readonly [
  zoom: number,
  activeWidth: number,
  inactiveWidth: number,
];

export function buildActiveAwareLineWidth({
  zoomStops,
}: {
  zoomStops: ActiveAwareLineWidthStop[];
}): ExpressionSpecification {
  const expression: unknown[] = ["interpolate", ["linear"], ["zoom"]];

  zoomStops.forEach(([zoom, activeWidth, inactiveWidth]) => {
    expression.push(
      zoom,
      ["case", ["boolean", ["get", "active"], false], activeWidth, inactiveWidth],
    );
  });

  return expression as ExpressionSpecification;
}
