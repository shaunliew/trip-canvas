export type MapPoint = {
  x: number;
  y: number;
};

export type MapViewport = {
  width: number;
  height: number;
};

export type MapCalloutSize = {
  width: number;
  height: number;
};

export type MapCalloutPositionInput = {
  marker: MapPoint;
  viewport: MapViewport;
  callout: MapCalloutSize;
  margin?: number;
  verticalGap?: number;
};

export type MapCalloutPosition = {
  left: number;
  top: number;
  anchorX: number;
};

const DEFAULT_MARGIN = 16;
const DEFAULT_VERTICAL_GAP = 24;

export function getMapCalloutPosition({
  marker,
  viewport,
  callout,
  margin = DEFAULT_MARGIN,
  verticalGap = DEFAULT_VERTICAL_GAP,
}: MapCalloutPositionInput): MapCalloutPosition {
  const maxLeft = Math.max(margin, viewport.width - callout.width - margin);
  const centeredLeft = marker.x - callout.width / 2;
  const left = clamp(Math.round(centeredLeft), margin, maxLeft);
  const preferredTop = marker.y - callout.height - verticalGap;
  const top =
    preferredTop >= margin
      ? preferredTop
      : Math.min(
          Math.max(marker.y + verticalGap, margin),
          Math.max(margin, viewport.height - callout.height - margin),
        );

  return {
    left,
    top: Math.round(top),
    anchorX: Math.round(marker.x - left),
  };
}

function clamp(value: number, min: number, max: number) {
  if (value < min) {
    return min;
  }

  if (value > max) {
    return max;
  }

  return value;
}
