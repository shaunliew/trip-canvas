export type BudgetLevel = "budget" | "mid_range" | "luxury";

export type BackendExtractedPlace = {
  name: string;
  category: string;
  city_or_region_guess: string;
  lat?: number | null;
  lng?: number | null;
  formatted_address?: string | null;
  confidence: number;
  evidence_caption_quote: string;
  source_url?: string | null;
  place_id?: string | null;
};

export type ExtractResponse = {
  places: BackendExtractedPlace[];
  source: "live" | "cache" | string;
  count: number;
};

export type UserPreferencesPayload = {
  start_date: string;
  end_date: string;
  budget_level: BudgetLevel;
  free_text: string;
  origin_city?: string | null;
};

export type HotelPreferencePayload = {
  chips: string[];
  free_text: string;
  optimize_for_me: boolean;
};

export type BaseAreaCandidate = {
  id: string;
  name: string;
  score: number;
  center: { lat: number; lng: number };
  transit_summary: string;
  rationale: string;
  tradeoffs: string[];
};

export type HotelCandidate = {
  id: string;
  name: string;
  base_area_id: string;
  lat: number | null;
  lng: number | null;
  price_summary: string;
  booking_url: string | null;
  rationale: string;
  tradeoffs: string[];
};

export type HotelBaseResult = {
  source: "live" | "cache";
  selected_base: BaseAreaCandidate;
  base_areas: BaseAreaCandidate[];
  hotel_candidates: HotelCandidate[];
  selected_hotel_id: string;
};

export type HotelBaseRequestPayload = {
  places: BackendExtractedPlace[];
  preferences: UserPreferencesPayload;
  hotel_preferences: HotelPreferencePayload;
};

export type ItineraryRequestPayload = {
  places: BackendExtractedPlace[];
  preferences: UserPreferencesPayload;
  hotel_base?: HotelBaseResult;
};

export type HotelBaseStreamEvent =
  | { type: "start"; destination?: string; place_count?: number }
  | { type: "stage"; stage?: string; msg?: string }
  | { type: "base_candidate"; candidate: BaseAreaCandidate }
  | { type: "hotel_candidate"; candidate: HotelCandidate }
  | { type: "result"; content: string; elapsed_s?: number }
  | { type: "error"; message: string }
  | { type: string; [key: string]: unknown };

export type ItineraryStreamEvent =
  | {
      type: "start";
      n_places_in?: number;
      n_places_used?: number;
      destination?: string;
    }
  | {
      type: "heartbeat";
      elapsed_s?: number;
    }
  | {
      type: "stage";
      stage: "weather" | "booking" | "narrator" | string;
      msg?: string;
    }
  | {
      type: "result";
      content: string;
      elapsed_s?: number;
    }
  | {
      type: "error";
      message: string;
    }
  | {
      type: string;
      [key: string]: unknown;
    };

// Weather (from spike_weather.py)
export type DayForecast = {
  date: string;
  temp_min_c: number;
  temp_max_c: number;
  precipitation_mm: number;
  summary: string;
};

export type WeatherReport = {
  destination: string;
  day_forecasts: DayForecast[];
};

export type WeatherAdjustment = {
  date: string;
  reason: string;
  moved_places: string[];
  weather_summary: string;
};

// Agentic payment (AP2 + x402, from spike_booking.py) — SEPARATE from booking fulfillment.
// Mock this round: is_mock_settlement=true ⇒ payment_status="mock" (never "settled").
export type PaymentSettlement = {
  settlement_id: string;
  payment_protocol: "ap2_x402";
  payment_network: string; // "mock" | "base-sepolia" | "base"
  payment_status: "mock" | "pending" | "settled" | "failed";
  amount_sgd?: number | null;
  is_mock_settlement: boolean;
  notes?: string;
};

// Booking (from spike_booking.py) — every item is_mock=true (fulfillment is simulated).
// status is fulfillment-only ("confirmed" only on the deprecated Duffel path); the agentic
// payment lives in `settlement`. `source` union is frozen — payment rail is in settlement.payment_protocol.
export type BookingItem = {
  booking_id: string;
  category: "flight" | "hotel" | "attraction";
  name: string;
  price_estimate_sgd: number | null;
  status: "confirmed" | "reserved";
  book_url: string;
  source: "duffel_sandbox" | "booking_deeplink" | "klook_deeplink";
  is_mock: boolean;
  notes: string;
  settlement?: PaymentSettlement | null;
};

export type BookingResult = {
  items: BookingItem[];
  total_estimate_sgd: number;
  is_mock: boolean;
  payment_protocol?: string;
  total_settled_sgd?: number;
  is_mock_settlement?: boolean;
};

// Agentic-payment (x402/AP2) summary carried on the itinerary (spike_planner.PaymentContext).
// Backend model is extra="allow", so additional keys may appear.
export type PaymentContext = {
  payment_protocol?: string; // e.g. "x402"
  network?: string; // e.g. "base-sepolia"
  asset?: string; // e.g. "USDC"
  agent_payment_usd?: string; // string in the cache, e.g. "0.01"
  mock_booking_only?: boolean;
  [key: string]: unknown;
};

// One of the 3 hotel recommendations on the itinerary (from spike_planner.py).
// Exactly one has is_best=true (the recommended_hotel / selected_hotel_id).
export type HotelOption = {
  id: string;
  name: string;
  base_area_id?: string;
  price_summary?: string;
  booking_url?: string | null;
  rationale?: string;
  tradeoffs?: string[];
  is_best: boolean;
};

// One time-blocked stop within an itinerary day (from spike_planner.DayStop).
// Anchors carry place_name (a source place) or category "hotel"; supporting
// stops have place_name null. Additive — legacy day payloads omit `stops`.
export type DayStop = {
  time_of_day: "morning" | "afternoon" | "evening";
  name: string;
  category:
    | "attraction"
    | "restaurant"
    | "cafe"
    | "hotel"
    | "transport"
    | "shopping"
    | "other";
  place_name?: string | null;
  description?: string;
};

export type BackendTripPayload = unknown;
