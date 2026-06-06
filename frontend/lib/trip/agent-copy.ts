import type { ExtractResponse } from "@/lib/trip/backend-types";
import type { TripDay, TripHotelBase, TripPlace } from "@/lib/trip/types";

export type GenerationStatusForCopy =
  | "idle_globe"
  | "extracting_places"
  | "zooming_to_destination"
  | "choosing_hotel_base"
  | "optimizing_hotel_base"
  | "planning_itinerary"
  | "trip_ready"
  | "error";

export type StageStep = {
  key: "extract" | "ground" | "base" | "plan" | "approve";
  label: string;
  detail: string;
  active: boolean;
  done: boolean;
};

type AgentLogLike = {
  detail: string;
};

type SteeringLike = {
  lockedPlaceIds: Set<string>;
};

const TRADEOFF_KEYWORDS = [
  "tradeoff",
  "long",
  "walk",
  "transit",
  "station",
  "weather",
  "rain",
  "dry",
  "far",
  "route",
  "transfer",
];

export function getStageSteps(
  status: GenerationStatusForCopy,
  hasPlaces: boolean,
): StageStep[] {
  return [
    {
      key: "extract",
      label: "Extract",
      detail: "Read Reels",
      active: status === "extracting_places",
      done: hasPlaces,
    },
    {
      key: "ground",
      label: "Ground",
      detail: "Map places",
      active: status === "zooming_to_destination",
      done: hasPlaces && status !== "extracting_places" && status !== "zooming_to_destination",
    },
    {
      key: "base",
      label: "Base",
      detail: "Choose hotel",
      active: status === "choosing_hotel_base" || status === "optimizing_hotel_base",
      done: status === "planning_itinerary" || status === "trip_ready",
    },
    {
      key: "plan",
      label: "Plan",
      detail: "Sequence days",
      active: status === "planning_itinerary",
      done: status === "trip_ready",
    },
    {
      key: "approve",
      label: "Approve",
      detail: "Book handoff",
      active: status === "trip_ready",
      done: status === "trip_ready",
    },
  ];
}

export function getAgentPanelTitle(status: GenerationStatusForCopy) {
  if (status === "extracting_places") {
    return "Finding real places";
  }

  if (status === "zooming_to_destination") {
    return "Grounding the map";
  }

  if (status === "planning_itinerary") {
    return "Sequencing the trip";
  }

  if (status === "choosing_hotel_base" || status === "optimizing_hotel_base") {
    return "Choosing the base";
  }

  if (status === "trip_ready") {
    return "Review and approve";
  }

  if (status === "error") {
    return "Needs attention";
  }

  return "Preparing";
}

export function buildSelectedPlaceDecision(place: TripPlace) {
  return `${place.name} is active on Day ${place.day} because the planner found it useful for the mapped route.`;
}

export function buildDecisionSummary(
  status: GenerationStatusForCopy,
  selectedPlace: TripPlace | null,
  hotelBase: TripHotelBase | undefined,
  logs: AgentLogLike[],
) {
  if (selectedPlace) {
    return buildSelectedPlaceDecision(selectedPlace);
  }

  if (hotelBase) {
    return `Selected ${hotelBase.selectedBaseName} as the trip base and ${hotelBase.selectedHotelName} as the hotel candidate.`;
  }

  const latestLog = logs.at(-1);
  if (latestLog?.detail) {
    return latestLog.detail;
  }

  if (status === "extracting_places") {
    return "Reading Reel captions and location signals before grounding places on the map.";
  }

  if (status === "choosing_hotel_base") {
    return "Extracted places are mapped; the agent is ready to score hotel base tradeoffs.";
  }

  return "Waiting for the backend agent to produce the next visible decision.";
}

export function buildEvidenceSummary(
  selectedPlace: TripPlace | null,
  extractResponse: Pick<ExtractResponse, "count" | "source"> | null,
) {
  if (selectedPlace?.evidenceQuote) {
    return truncateText(`Reel evidence: "${selectedPlace.evidenceQuote}"`, 150);
  }

  if (typeof selectedPlace?.confidence === "number") {
    return `Extraction confidence is ${Math.round(selectedPlace.confidence * 100)}%.`;
  }

  if (extractResponse) {
    return `${extractResponse.count} extracted places are using ${extractResponse.source} source data.`;
  }

  return "No source evidence has been returned yet.";
}

export function buildTradeoffSummary(
  selectedPlace: TripPlace | null,
  selectedDay: TripDay | null,
  hotelBase?: TripHotelBase,
) {
  if (selectedPlace) {
    const text = [
      selectedPlace.dayPlanText,
      selectedPlace.plannerSummary,
      selectedDay?.summary,
      selectedDay?.weatherStrategy,
    ]
      .filter(Boolean)
      .join(" ");
    const tradeoff = findRelevantSentence(text, TRADEOFF_KEYWORDS);

    if (tradeoff) {
      return truncateText(tradeoff, 150);
    }

    if (selectedPlace.address) {
      return `Routing detail is limited; use the mapped address for transit review: ${selectedPlace.address}.`;
    }

    return "No explicit route or timing tradeoff was returned for this stop.";
  }

  if (hotelBase?.selectedBaseRationale) {
    return truncateText(hotelBase.selectedBaseRationale, 150);
  }

  return "Tradeoffs will appear once a hotel base or mapped stop is selected.";
}

export function buildNextActionSummary(
  status: GenerationStatusForCopy,
  selectedPlace: TripPlace | null,
  steering: SteeringLike,
) {
  if (status === "error") {
    return "Fix the input or retry the generation flow.";
  }

  if (status === "planning_itinerary") {
    return "Wait for the planner result; steering edits will be saved for the next run.";
  }

  if (status === "trip_ready") {
    return "Approve the plan when the map, rationale, and hotel base look right.";
  }

  if (selectedPlace) {
    return steering.lockedPlaceIds.has(selectedPlace.id)
      ? `Review ${selectedPlace.name}, or unlock it before the next generation.`
      : `Lock ${selectedPlace.name}, request a Day ${selectedPlace.day} regeneration, or add a steering note.`;
  }

  if (status === "choosing_hotel_base") {
    return "Choose hotel-base priorities, then let the optimizer score the mapped places.";
  }

  return "Select a mapped stop to inspect the agent rationale and steering controls.";
}

export function formatPriorityTheme(theme: string) {
  const labels: Record<string, string> = {
    food: "Food",
    transit: "Transit",
    value: "Value",
    weather: "Weather",
  };

  return labels[theme] ?? theme;
}

function findRelevantSentence(text: string, keywords: string[]) {
  return splitSentences(text).find((sentence) => {
    const lower = sentence.toLowerCase();
    return keywords.some((keyword) => lower.includes(keyword));
  }) ?? "";
}

function splitSentences(text: string) {
  return text
    .split(/(?<=[.!?])\s+|;\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function truncateText(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
}
