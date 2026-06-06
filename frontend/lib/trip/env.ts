export function readPublicMapboxToken() {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim().replace(/^=+/, "") ?? "";
  return token.length > 0 ? token : undefined;
}
