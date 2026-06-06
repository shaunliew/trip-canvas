import {
  PLACE_CATEGORIES,
  type PlaceCategory,
  type TripDay,
  type TripDayStop,
  type TripDayStopCategory,
  type TripDestination,
  type TripExperience,
  type TripPlace,
  type TripRoute,
  type TripSourceReel,
} from "@/lib/trip/types";

type AnyRecord = Record<string, unknown>;

const DEFAULT_TRIP = {
  id: "tokyo-demo",
  title: "Tokyo Reel Trip",
  datesLabel: "4 days in June",
  destination: {
    city: "Tokyo",
    country: "Japan",
    center: [139.7671, 35.6812] satisfies [number, number],
    zoom: 11.15,
  },
};

const CATEGORY_SET = new Set<string>(PLACE_CATEGORIES);

export function normalizeTripFromBackend(raw: unknown): TripExperience {
  const record = asRecord(raw);

  if (!record) {
    throw new Error("Trip payload must be an object.");
  }

  const compositeTrip = tryNormalizeCompositePlannerTrip(record);
  if (compositeTrip) {
    return compositeTrip;
  }

  return normalizeStructuredTrip(record);
}

export function normalizePlaceCategory(value: unknown): PlaceCategory {
  const normalized = readString(value)
    .toLowerCase()
    .trim()
    .replace(/[\s_]+/g, "-");

  if (CATEGORY_SET.has(normalized)) {
    return normalized as PlaceCategory;
  }

  return "other";
}

function normalizeStructuredTrip(record: AnyRecord): TripExperience {
  const placeRecords = readArray(record.places);
  const dayRecords = readArray(record.itineraryDays ?? record.days);
  const dayReferenceMap = buildDayReferenceMap(dayRecords);
  const places = placeRecords
    .map((place, index) => normalizePlace(place, index, dayReferenceMap))
    .filter((place): place is TripPlace => Boolean(place));

  if (places.length === 0) {
    throw new Error("Trip payload did not include any valid places.");
  }

  const days = normalizeDays(dayRecords, places);
  const destination = normalizeDestination(record.destination);
  const title = readString(record.title) || DEFAULT_TRIP.title;
  const datesLabel =
    readString(record.datesLabel) ||
    readString(record.dates) ||
    DEFAULT_TRIP.datesLabel;
  const id =
    readString(record.id) ||
    readString(record.tripId) ||
    slugify(title) ||
    DEFAULT_TRIP.id;
  const sourceReels = normalizeSourceReels(record.sourceReels, places);
  const hotelBase = normalizeHotelBase(record.hotelBase ?? record.hotel_base);
  const weatherAdjustments = normalizeWeatherAdjustments(
    record.weatherAdjustments ?? record.weather_adjustments,
  );

  return {
    id,
    title,
    destination,
    datesLabel,
    days,
    places,
    ...(sourceReels.length > 0 ? { sourceReels } : {}),
    ...(hotelBase ? { hotelBase } : {}),
    ...(weatherAdjustments.length > 0 ? { weatherAdjustments } : {}),
  };
}

function tryNormalizeCompositePlannerTrip(
  record: AnyRecord,
): TripExperience | null {
  const plannerRecord = asRecord(
    record.itinerary ?? record.plannerOutput ?? record.planner_output,
  );

  if (!plannerRecord) {
    return null;
  }

  const extractedPlaces = readArray(
    record.extractedPlaces ?? record.extracted_places ?? record.places,
  );
  const plannerPlaces = readArray(plannerRecord.places);
  const plannerDays = readArray(plannerRecord.days);
  const summaryByName = new Map<string, AnyRecord>();
  const sourcePlaceNames = readArray(plannerRecord.source_places)
    .map((name) => readString(name).toLowerCase())
    .filter(Boolean);

  plannerPlaces.forEach((place) => {
    const placeRecord = asRecord(place);
    const name = readString(placeRecord?.name);
    if (name && placeRecord) {
      summaryByName.set(name.toLowerCase(), placeRecord);
    }
  });

  const dayByName = buildPlannerDayByName(plannerDays, [
    ...summaryByName.keys(),
    ...sourcePlaceNames,
  ]);
  const dayTextByName = buildPlannerDayTextByName(plannerDays, [
    ...summaryByName.keys(),
    ...sourcePlaceNames,
  ]);
  const plannedPlaceNames = new Set([
    ...summaryByName.keys(),
    ...sourcePlaceNames,
  ]);

  if (dayByName.size === 0) {
    throw new Error(
      "Composite planner payload could not match places to days.",
    );
  }

  const places = extractedPlaces
    .filter((place) => {
      const placeRecord = asRecord(place);
      const name = readString(placeRecord?.name).toLowerCase();

      return plannedPlaceNames.size === 0 || plannedPlaceNames.has(name);
    })
    .map((place, index) => {
      const placeRecord = asRecord(place);
      const name = readString(placeRecord?.name);
      const plannerInfo = summaryByName.get(name.toLowerCase());
      const plannerSummary = readString(plannerInfo?.summary);
      const merged = {
        ...placeRecord,
        day: dayByName.get(name.toLowerCase()),
        day_plan_text: dayTextByName.get(name.toLowerCase()),
        planner_summary: plannerSummary,
        summary:
          plannerSummary ||
          readString(placeRecord?.summary) ||
          readString(placeRecord?.evidence_caption_quote),
        source_url:
          readString(plannerInfo?.source_url) ||
          readString(placeRecord?.source_url),
      };

      return normalizePlace(merged, index, new Map());
    })
    .filter((place): place is TripPlace => Boolean(place));

  if (
    places.length === 0 ||
    places.some((place) => !dayByName.has(place.name.toLowerCase()))
  ) {
    throw new Error(
      "Composite planner payload did not include enough matched valid places.",
    );
  }

  const hotelBase = normalizeHotelBase(
    record.hotelBase ?? record.hotel_base ?? plannerRecord.hotel_base,
  );
  const weatherAdjustments = normalizeWeatherAdjustments(
    plannerRecord.weather_adjustments ?? plannerRecord.weatherAdjustments,
  );

  return {
    id: readString(record.id) || readString(record.tripId) || DEFAULT_TRIP.id,
    title:
      readString(plannerRecord.title) ||
      readString(record.title) ||
      DEFAULT_TRIP.title,
    destination: normalizeDestination(record.destination),
    datesLabel:
      readString(record.datesLabel) ||
      readString(record.dates) ||
      DEFAULT_TRIP.datesLabel,
    days: normalizeDays(plannerDays, places),
    places,
    ...(hotelBase ? { hotelBase } : {}),
    ...(weatherAdjustments.length > 0 ? { weatherAdjustments } : {}),
  };
}

function normalizeDestination(destination: unknown): TripDestination {
  const destinationRecord = asRecord(destination);
  const center = readCenter(destinationRecord?.center);
  const zoom = readFiniteNumber(destinationRecord?.zoom);

  return {
    city: readString(destinationRecord?.city) || DEFAULT_TRIP.destination.city,
    country:
      readString(destinationRecord?.country) ||
      DEFAULT_TRIP.destination.country,
    center: center ?? DEFAULT_TRIP.destination.center,
    zoom: zoom ?? DEFAULT_TRIP.destination.zoom,
  };
}

function normalizePlace(
  rawPlace: unknown,
  index: number,
  dayReferenceMap: Map<string, number>,
): TripPlace | null {
  const place = asRecord(rawPlace);

  if (!place) {
    return null;
  }

  const name = readString(place.name);
  const lat = readFiniteNumber(place.lat);
  const lng = readFiniteNumber(place.lng);

  if (
    !name ||
    lat === null ||
    lng === null ||
    !isValidLat(lat) ||
    !isValidLng(lng)
  ) {
    return null;
  }

  const id =
    readString(place.id) ||
    readString(place.place_id) ||
    slugify(name) ||
    `place-${index + 1}`;
  const category = normalizePlaceCategory(place.category ?? place.type);
  const day =
    readDayNumber(place.day) ??
    dayReferenceMap.get(id.toLowerCase()) ??
    dayReferenceMap.get(name.toLowerCase()) ??
    dayReferenceMap.get(slugify(name)) ??
    1;

  return {
    id,
    name,
    category,
    day,
    lat,
    lng,
    summary:
      readString(place.summary) ||
      readString(place.evidence_caption_quote) ||
      "A saved place from this trip.",
    ...(readString(place.address ?? place.formatted_address)
      ? { address: readString(place.address ?? place.formatted_address) }
      : {}),
    ...(readString(
      place.evidenceQuote ??
        place.evidence_quote ??
        place.evidence_caption_quote,
    )
      ? {
          evidenceQuote: readString(
            place.evidenceQuote ??
              place.evidence_quote ??
              place.evidence_caption_quote,
          ),
        }
      : {}),
    ...(readString(place.plannerSummary ?? place.planner_summary)
      ? {
          plannerSummary: readString(
            place.plannerSummary ?? place.planner_summary,
          ),
        }
      : {}),
    ...(readString(place.dayPlanText ?? place.day_plan_text)
      ? { dayPlanText: readString(place.dayPlanText ?? place.day_plan_text) }
      : {}),
    ...(readString(place.sourceUrl ?? place.source_url)
      ? { sourceUrl: readString(place.sourceUrl ?? place.source_url) }
      : {}),
    ...(readString(place.sourceReelUrl ?? place.source_reel_url)
      ? {
          sourceReelUrl: readString(
            place.sourceReelUrl ?? place.source_reel_url,
          ),
        }
      : {}),
    ...(readFiniteNumber(place.confidence) !== null
      ? { confidence: readFiniteNumber(place.confidence) as number }
      : {}),
  };
}

const STOP_CATEGORY_SET = new Set<TripDayStopCategory>([
  "attraction",
  "restaurant",
  "cafe",
  "hotel",
  "transport",
  "shopping",
  "other",
]);
const STOP_TIME_SET = new Set<TripDayStop["timeOfDay"]>([
  "morning",
  "afternoon",
  "evening",
]);

function normalizeStops(rawStops: unknown): TripDayStop[] {
  return readArray(rawStops)
    .map((rawStop): TripDayStop | null => {
      const stop = asRecord(rawStop);
      if (!stop) return null;
      const name = readString(stop.name);
      if (!name) return null;

      const rawTime = readString(
        stop.time_of_day ?? stop.timeOfDay,
      ).toLowerCase();
      const timeOfDay = (
        STOP_TIME_SET.has(rawTime as TripDayStop["timeOfDay"])
          ? rawTime
          : "morning"
      ) as TripDayStop["timeOfDay"];

      const rawCategory = readString(stop.category).toLowerCase();
      const category = (
        STOP_CATEGORY_SET.has(rawCategory as TripDayStopCategory)
          ? rawCategory
          : "other"
      ) as TripDayStopCategory;

      const placeName = readString(stop.place_name ?? stop.placeName);
      const description = readString(stop.description);

      return {
        timeOfDay,
        name,
        category,
        isAnchor: Boolean(placeName) || category === "hotel",
        ...(placeName ? { placeName } : {}),
        ...(description ? { description } : {}),
      };
    })
    .filter((stop): stop is TripDayStop => stop !== null);
}

function normalizeDays(rawDays: unknown[], places: TripPlace[]): TripDay[] {
  const placeByReference = new Map<string, TripPlace>();
  places.forEach((place) => {
    placeByReference.set(place.id.toLowerCase(), place);
    placeByReference.set(place.name.toLowerCase(), place);
    placeByReference.set(slugify(place.name), place);
  });

  const days = rawDays
    .map((rawDay, index) => {
      const dayRecord = asRecord(rawDay);
      const day =
        readDayNumber(dayRecord?.day ?? dayRecord?.day_number) ?? index + 1;
      const rawPlaceIds = readArray(dayRecord?.placeIds ?? dayRecord?.place_ids)
        .map((placeId) => readString(placeId))
        .filter(Boolean);
      const matchedPlaceIds = rawPlaceIds
        .map((placeId) => placeByReference.get(placeId.toLowerCase())?.id)
        .filter((placeId): placeId is string => Boolean(placeId));
      const derivedPlaceIds = places
        .filter((place) => place.day === day)
        .map((place) => place.id);
      const placeIds = uniqueStrings(
        matchedPlaceIds.length > 0 ? matchedPlaceIds : derivedPlaceIds,
      );
      const route = normalizeRoute(dayRecord?.route);
      const stops = normalizeStops(dayRecord?.stops);

      return {
        day,
        title: readString(dayRecord?.title) || `Day ${day}`,
        summary:
          readString(dayRecord?.summary) ||
          readString(dayRecord?.narration) ||
          readString(dayRecord?.activities) ||
          "",
        placeIds,
        ...(stops.length > 0 ? { stops } : {}),
        ...(route ? { route } : {}),
        ...(readString(
          dayRecord?.weather_strategy ?? dayRecord?.weatherStrategy,
        )
          ? {
              weatherStrategy: readString(
                dayRecord?.weather_strategy ?? dayRecord?.weatherStrategy,
              ),
            }
          : {}),
      };
    })
    .filter((day) => day.placeIds.length > 0);

  if (days.length > 0) {
    return days.sort((a, b) => a.day - b.day);
  }

  return Array.from(new Set(places.map((place) => place.day)))
    .sort((a, b) => a - b)
    .map((day) => ({
      day,
      title: `Day ${day}`,
      summary: "",
      placeIds: places
        .filter((place) => place.day === day)
        .map((place) => place.id),
    }));
}

function normalizeRoute(rawRoute: unknown): TripRoute | null {
  const route = asRecord(rawRoute);

  if (!route) {
    return null;
  }

  const coordinates = readArray(route.coordinates)
    .map(readLngLatCoordinate)
    .filter((coordinate): coordinate is [number, number] =>
      Boolean(coordinate),
    );

  if (coordinates.length < 2) {
    return null;
  }

  const durationMinutes = readFiniteNumber(
    route.durationMinutes ?? route.duration_minutes,
  );
  const distanceKm = readFiniteNumber(route.distanceKm ?? route.distance_km);

  return {
    coordinates,
    ...(durationMinutes !== null ? { durationMinutes } : {}),
    ...(distanceKm !== null ? { distanceKm } : {}),
  };
}

function normalizeSourceReels(
  rawSourceReels: unknown,
  places: TripPlace[],
): TripSourceReel[] {
  const placeByName = new Map(
    places.map((place) => [place.name.toLowerCase(), place.id]),
  );

  return readArray(rawSourceReels)
    .map((sourceReel, index) => {
      const reel = asRecord(sourceReel);
      const url = readString(reel?.url);

      if (!url) {
        return null;
      }

      const extractedNames = readArray(
        reel?.extractedPlaces ?? reel?.extracted_places,
      )
        .map((placeName) => readString(placeName).toLowerCase())
        .filter(Boolean);

      return {
        id: readString(reel?.id) || `reel-${index + 1}`,
        url,
        ...(readString(reel?.thumbnailUrl ?? reel?.thumbnail_url)
          ? {
              thumbnailUrl: readString(
                reel?.thumbnailUrl ?? reel?.thumbnail_url,
              ),
            }
          : {}),
        extractedPlaceIds: extractedNames
          .map((placeName) => placeByName.get(placeName))
          .filter((placeId): placeId is string => Boolean(placeId)),
      };
    })
    .filter((sourceReel): sourceReel is TripSourceReel => Boolean(sourceReel));
}

function normalizeHotelBase(rawHotelBase: unknown) {
  const hotelBase = asRecord(rawHotelBase);
  if (!hotelBase) {
    return undefined;
  }

  const baseAreas = readArray(hotelBase.base_areas ?? hotelBase.baseAreas)
    .map(asRecord)
    .filter((base): base is AnyRecord => Boolean(base))
    .map((base) => {
      const center = asRecord(base.center);
      const validCenter = readValidLatLng(center?.lat, center?.lng);

      return {
        id: readString(base.id),
        name: readString(base.name),
        score: readFiniteNumber(base.score) ?? 0,
        ...(validCenter
          ? {
              center: validCenter,
            }
          : {}),
        rationale: readString(base.rationale),
        tradeoffs: readArray(base.tradeoffs).map(readString).filter(Boolean),
      };
    })
    .filter((base) => base.id && base.name);
  const hotels = readArray(
    hotelBase.hotel_candidates ?? hotelBase.hotelCandidates,
  )
    .map(asRecord)
    .filter((hotel): hotel is AnyRecord => Boolean(hotel));
  const hotelEntries = hotels
    .map((hotel) => {
      const validCoordinates = readValidLatLng(hotel.lat, hotel.lng);
      const baseAreaId = readString(hotel.base_area_id ?? hotel.baseAreaId);

      return {
        candidate: {
          id: readString(hotel.id),
          name: readString(hotel.name),
          baseAreaId,
          ...(validCoordinates
            ? {
                lat: validCoordinates.lat,
                lng: validCoordinates.lng,
              }
            : {}),
          priceSummary: readString(hotel.price_summary ?? hotel.priceSummary),
          ...(readString(hotel.booking_url ?? hotel.bookingUrl)
            ? { bookingUrl: readString(hotel.booking_url ?? hotel.bookingUrl) }
            : {}),
          rationale: readString(hotel.rationale),
          tradeoffs: readArray(hotel.tradeoffs).map(readString).filter(Boolean),
        },
        baseAreaId,
      };
    })
    .filter((hotel) => hotel.candidate.id && hotel.candidate.name);
  const hotelCandidates = hotelEntries.map((hotel) => hotel.candidate);
  const selectedBase = asRecord(
    hotelBase.selected_base ?? hotelBase.selectedBase,
  );
  const selectedBaseId = readString(selectedBase?.id);
  const selectedHotelId = readString(
    hotelBase.selected_hotel_id ?? hotelBase.selectedHotelId,
  );
  const selectedHotel =
    hotelEntries.find((hotel) => hotel.candidate.id === selectedHotelId) ??
    null;
  const selectedBaseName = readString(selectedBase?.name);
  const selectedHotelName = readString(selectedHotel?.candidate.name);

  if (
    !selectedBaseName ||
    !selectedHotelName ||
    !selectedHotel ||
    baseAreas.length === 0 ||
    hotelCandidates.length === 0 ||
    (selectedHotel.baseAreaId && selectedHotel.baseAreaId !== selectedBaseId)
  ) {
    return undefined;
  }

  return {
    selectedBaseId,
    selectedBaseName,
    selectedBaseRationale: readString(selectedBase?.rationale),
    selectedHotelId,
    selectedHotelName,
    selectedHotelRationale: selectedHotel.candidate.rationale,
    baseAreas,
    hotelCandidates,
  };
}

function normalizeWeatherAdjustments(rawAdjustments: unknown) {
  return readArray(rawAdjustments)
    .map(asRecord)
    .filter((adjustment): adjustment is AnyRecord => Boolean(adjustment))
    .map((adjustment) => ({
      date: readString(adjustment.date),
      reason: readString(adjustment.reason),
      movedPlaces: readArray(adjustment.moved_places ?? adjustment.movedPlaces)
        .map(readString)
        .filter(Boolean),
      weatherSummary: readString(
        adjustment.weather_summary ?? adjustment.weatherSummary,
      ),
    }))
    .filter((adjustment) => adjustment.date && adjustment.reason);
}

function readValidLatLng(rawLat: unknown, rawLng: unknown) {
  const lat = readFiniteNumber(rawLat);
  const lng = readFiniteNumber(rawLng);

  if (lat === null || lng === null || !isValidLatLng(lat, lng)) {
    return null;
  }

  return { lat, lng };
}

function isValidLatLng(lat: number, lng: number) {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

function buildDayReferenceMap(rawDays: unknown[]): Map<string, number> {
  const dayReferenceMap = new Map<string, number>();

  rawDays.forEach((rawDay, index) => {
    const dayRecord = asRecord(rawDay);
    const day =
      readDayNumber(dayRecord?.day ?? dayRecord?.day_number) ?? index + 1;
    const placeIds = readArray(dayRecord?.placeIds ?? dayRecord?.place_ids);

    placeIds.forEach((placeId) => {
      const value = readString(placeId);
      if (value) {
        dayReferenceMap.set(value.toLowerCase(), day);
        dayReferenceMap.set(slugify(value), day);
      }
    });
  });

  return dayReferenceMap;
}

function buildPlannerDayByName(
  rawDays: unknown[],
  placeNames: string[],
): Map<string, number> {
  const dayByName = new Map<string, number>();
  const uniquePlaceNames = uniqueStrings(placeNames.filter(Boolean));

  rawDays.forEach((rawDay, index) => {
    const dayRecord = asRecord(rawDay);
    const day =
      readDayNumber(dayRecord?.day ?? dayRecord?.day_number) ?? index + 1;
    const dayText = [
      dayRecord?.title,
      dayRecord?.summary,
      dayRecord?.activities,
      dayRecord?.narration,
    ]
      .map(readString)
      .join(" ")
      .toLowerCase();

    uniquePlaceNames.forEach((placeName) => {
      if (dayText.includes(placeName)) {
        dayByName.set(placeName, day);
      }
    });
  });

  return dayByName;
}

function buildPlannerDayTextByName(
  rawDays: unknown[],
  placeNames: string[],
): Map<string, string> {
  const dayTextByName = new Map<string, string>();
  const uniquePlaceNames = uniqueStrings(placeNames.filter(Boolean));

  rawDays.forEach((rawDay) => {
    const dayRecord = asRecord(rawDay);
    const dayText = [
      dayRecord?.title,
      dayRecord?.summary,
      dayRecord?.activities,
      dayRecord?.narration,
    ]
      .map(readString)
      .filter(Boolean)
      .join(" ");
    const lowerDayText = dayText.toLowerCase();

    uniquePlaceNames.forEach((placeName) => {
      if (lowerDayText.includes(placeName) && dayText) {
        dayTextByName.set(placeName, dayText);
      }
    });
  });

  return dayTextByName;
}

function readCenter(value: unknown): [number, number] | null {
  if (Array.isArray(value) && value.length >= 2) {
    const lng = readFiniteNumber(value[0]);
    const lat = readFiniteNumber(value[1]);
    return lng !== null && lat !== null && isValidLng(lng) && isValidLat(lat)
      ? [lng, lat]
      : null;
  }

  const center = asRecord(value);
  const lat = readFiniteNumber(center?.lat);
  const lng = readFiniteNumber(center?.lng);

  return lng !== null && lat !== null && isValidLng(lng) && isValidLat(lat)
    ? [lng, lat]
    : null;
}

function readLngLatCoordinate(value: unknown): [number, number] | null {
  if (!Array.isArray(value) || value.length < 2) {
    return null;
  }

  const lng = readFiniteNumber(value[0]);
  const lat = readFiniteNumber(value[1]);

  return lng !== null && lat !== null && isValidLng(lng) && isValidLat(lat)
    ? [lng, lat]
    : null;
}

function asRecord(value: unknown): AnyRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as AnyRecord)
    : null;
}

function readArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function readString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function readDayNumber(value: unknown): number | null {
  const day = readFiniteNumber(value);
  return day !== null && day > 0 ? Math.trunc(day) : null;
}

function isValidLat(value: number) {
  return value >= -90 && value <= 90;
}

function isValidLng(value: number) {
  return value >= -180 && value <= 180;
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values));
}
