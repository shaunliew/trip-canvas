import type {
  BackendExtractedPlace,
  HotelBaseResult,
} from "@/lib/trip/backend-types";

export const DEMO_REEL_URLS = [
  "https://www.instagram.com/reel/DYbmT-SNzVK/",
  "https://www.instagram.com/reel/DYM_I5IvLSv/",
  "https://www.instagram.com/reel/DYGH3jFBZHz/",
  "https://www.instagram.com/reel/DXwcVVliX3B/",
] as const;

export const DEMO_REEL_INPUT = DEMO_REEL_URLS.join("\n");

export type DemoCacheResponse = {
  source: "cache" | string;
  places: BackendExtractedPlace[];
  hotel_base: HotelBaseResult;
  itinerary: unknown;
};

export async function loadBackendDemoCache(signal?: AbortSignal): Promise<DemoCacheResponse> {
  const response = await fetch(`${getBackendBaseUrl()}/demo-cache`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(await formatDemoCacheError(response));
  }

  return response.json() as Promise<DemoCacheResponse>;
}

function getBackendBaseUrl() {
  return (process.env.NEXT_PUBLIC_BACKEND_URL?.trim() || "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

async function formatDemoCacheError(response: Response) {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }
  } catch {
    // Fall back to the status-based message below.
  }

  return `Demo cache failed with HTTP ${response.status}.`;
}
