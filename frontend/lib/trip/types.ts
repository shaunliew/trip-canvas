export const PLACE_CATEGORIES = [
  "landmark",
  "crossing",
  "temple",
  "shrine",
  "market",
  "restaurant",
  "hotel",
  "attraction",
  "transport",
  "activity",
  "station",
  "other",
] as const;

export type PlaceCategory = (typeof PLACE_CATEGORIES)[number];
export type TripDayNumber = number;
export type DayFilter = "all" | TripDayNumber;
export type CategoryFilter = "all" | PlaceCategory;

export type TripDestination = {
  city: string;
  country: string;
  center: [lng: number, lat: number];
  zoom: number;
};

export type TripSourceReel = {
  id: string;
  url: string;
  thumbnailUrl?: string;
  extractedPlaceIds: string[];
};

export type TripRoute = {
  coordinates: [lng: number, lat: number][];
  durationMinutes?: number;
  distanceKm?: number;
};

export type TripHotelBase = {
  selectedBaseId: string;
  selectedBaseName: string;
  selectedBaseRationale: string;
  selectedHotelId: string;
  selectedHotelName: string;
  selectedHotelRationale: string;
  baseAreas: {
    id: string;
    name: string;
    score: number;
    center?: {
      lat: number;
      lng: number;
    };
    rationale: string;
    tradeoffs: string[];
  }[];
  hotelCandidates: {
    id: string;
    name: string;
    baseAreaId: string;
    lat?: number;
    lng?: number;
    priceSummary: string;
    bookingUrl?: string;
    rationale: string;
    tradeoffs: string[];
  }[];
};

export type TripWeatherAdjustment = {
  date: string;
  reason: string;
  movedPlaces: string[];
  weatherSummary: string;
};

export type TripPlace = {
  id: string;
  name: string;
  category: PlaceCategory;
  day: TripDayNumber;
  lat: number;
  lng: number;
  summary: string;
  address?: string;
  evidenceQuote?: string;
  plannerSummary?: string;
  dayPlanText?: string;
  sourceUrl?: string;
  sourceReelUrl?: string;
  confidence?: number;
};

export type TripDayStopCategory =
  | "attraction"
  | "restaurant"
  | "cafe"
  | "hotel"
  | "transport"
  | "shopping"
  | "other";

export type TripDayStop = {
  timeOfDay: "morning" | "afternoon" | "evening";
  name: string;
  category: TripDayStopCategory;
  isAnchor: boolean; // a reel source place or the hotel (vs a supporting find)
  placeName?: string; // set iff this stop is a source place
  description?: string;
};

export type TripDay = {
  day: TripDayNumber;
  title: string;
  summary: string;
  placeIds: string[];
  stops?: TripDayStop[]; // ~3 time-blocked stops; undefined for legacy payloads
  route?: TripRoute;
  weatherStrategy?: string;
};

export type TripExperience = {
  id: string;
  title: string;
  destination: TripDestination;
  datesLabel: string;
  days: TripDay[];
  places: TripPlace[];
  sourceReels?: TripSourceReel[];
  hotelBase?: TripHotelBase;
  weatherAdjustments?: TripWeatherAdjustment[];
};
