"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type {
  AnyLayer,
  ExpressionSpecification,
  GeoJSONSource,
  Map,
  MapEventOf,
  MapLayerMouseEvent,
} from "mapbox-gl";
import { coerceSafeMapCenter, isValidLngLatValue } from "@/lib/trip/geo";
import {
  getMapCalloutPosition,
  type MapCalloutPosition,
} from "@/lib/trip/map-overlay";
import { buildActiveAwareLineWidth } from "@/lib/trip/map-style";
import type { DayFilter, TripDay, TripHotelBase, TripPlace } from "@/lib/trip/types";

export type TripMapMode = "globe" | "extracting" | "trip";

type TripMapProps = {
  mode?: TripMapMode;
  mapboxToken: string;
  center: {
    lat: number;
    lng: number;
  };
  initialZoom: number;
  days: TripDay[];
  selectedDay: DayFilter;
  selectedRouteDay?: TripDay["day"] | null;
  places: TripPlace[];
  selectedPlace: TripPlace | null;
  hotelBase?: TripHotelBase;
  onSelectPlace: (placeId: string) => void;
  onRegionFocusComplete?: () => void;
};

type RouteFeatureProperties = {
  day: number;
  active: boolean;
};
type RouteFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.LineString,
  RouteFeatureProperties
>;
type PlaceFeatureProperties = {
  placeId: string;
  name: string;
  category: TripPlace["category"];
  day: number;
  glyph: string;
  selected: boolean;
  muted: boolean;
};
type PlaceFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Point,
  PlaceFeatureProperties
>;
type HotelHubFeatureProperties = {
  name: string;
  glyph: string;
  kind: "hotel" | "base";
};
type HotelHubFeatureCollection = GeoJSON.FeatureCollection<
  GeoJSON.Point,
  HotelHubFeatureProperties
>;
type SelectedPlaceCalloutLayout = MapCalloutPosition & {
  width: number;
  height: number;
  markerY: number;
};

const STANDARD_DAY_PITCH = 56;
const STANDARD_DAY_BEARING = -22;
const SELECTED_PLACE_PITCH = 60;
const SELECTED_PLACE_BEARING = -30;
const GLOBE_ZOOM = 1.28;
const GLOBE_PITCH = 0;
const GLOBE_BEARING = -24;
const GLOBE_ROTATION_SPEED = 0.035;
const STANDARD_ARCHITECTURAL_BASEMAP_CONFIG = {
  lightPreset: "day",
  theme: "default",
  show3dBuildings: true,
  show3dFacades: true,
  show3dLandmarks: true,
  show3dTrees: false,
  showPlaceLabels: true,
  showPointOfInterestLabels: true,
  showLandmarkIcons: true,
  showLandmarkIconLabels: true,
  showRoadLabels: true,
  showTransitLabels: true,
  showPedestrianRoads: true,
};
const USE_SAFE_3D_FALLBACK = false;
const RELIABLE_BUILDINGS_LAYER_ID = "tripcanvas-reliable-3d-buildings";
const ROUTE_SOURCE_ID = "tripcanvas-routes";
const ROUTE_CASING_LAYER_ID = "tripcanvas-routes-casing";
const ROUTE_UNDERLAY_LAYER_ID = "tripcanvas-routes-underlay";
const ROUTE_ACTIVE_LAYER_ID = "tripcanvas-routes-active";
const ROUTE_ACTIVE_DASH_LAYER_ID = "tripcanvas-routes-active-dash";
const PLACE_SOURCE_ID = "tripcanvas-places";
const PLACE_CLUSTER_LAYER_ID = "tripcanvas-place-clusters";
const PLACE_CLUSTER_COUNT_LAYER_ID = "tripcanvas-place-cluster-counts";
const PLACE_CLUSTER_HITBOX_LAYER_ID = "tripcanvas-place-cluster-hitbox";
const PLACE_SELECTED_PULSE_LAYER_ID = "tripcanvas-place-selected-pulse";
const PLACE_HALO_LAYER_ID = "tripcanvas-place-halos";
const PLACE_DOT_LAYER_ID = "tripcanvas-place-dots";
const PLACE_GLYPH_LAYER_ID = "tripcanvas-place-glyphs";
const PLACE_HITBOX_LAYER_ID = "tripcanvas-place-hitbox";
const HOTEL_HUB_SOURCE_ID = "tripcanvas-hotel-hub";
const HOTEL_HUB_HALO_LAYER_ID = "tripcanvas-hotel-hub-halo";
const HOTEL_HUB_DOT_LAYER_ID = "tripcanvas-hotel-hub-dot";
const HOTEL_HUB_RING_LAYER_ID = "tripcanvas-hotel-hub-ring";
const HOTEL_HUB_GLYPH_LAYER_ID = "tripcanvas-hotel-hub-glyph";
const HOTEL_HUB_LABEL_LAYER_ID = "tripcanvas-hotel-hub-label";
const EMPTY_ROUTE_COLLECTION: RouteFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
const EMPTY_PLACE_COLLECTION: PlaceFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
const EMPTY_HOTEL_HUB_COLLECTION: HotelHubFeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
const ROUTE_DASH_SEQUENCE: number[][] = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 0.5, 3, 3.5],
  [0, 1, 3, 3],
  [0, 1.5, 3, 2.5],
  [0, 2, 3, 2],
  [0, 2.5, 3, 1.5],
  [0, 3, 3, 1],
  [0, 3.5, 3, 0.5],
];

export function TripMap({
  mode = "trip",
  mapboxToken,
  center,
  initialZoom,
  days,
  selectedDay,
  selectedRouteDay,
  places,
  selectedPlace,
  hotelBase,
  onSelectPlace,
  onRegionFocusComplete,
}: TripMapProps) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const onSelectPlaceRef = useRef(onSelectPlace);
  const onRegionFocusCompleteRef = useRef(onRegionFocusComplete);
  const cleanupMapRuntimeGuardsRef = useRef<(() => void) | null>(null);
  const previousFlyToPlaceIdRef = useRef<string | null>(null);
  const focusedPlaceSignatureRef = useRef<string | null>(null);
  const autoRotateFrameRef = useRef<number | null>(null);
  const selectedPulseFrameRef = useRef<number | null>(null);
  const routeDashFrameRef = useRef<number | null>(null);
  const prefersReducedMotionRef = useRef(false);
  const [mapReady, setMapReady] = useState(false);
  const [selectedCalloutLayout, setSelectedCalloutLayout] =
    useState<SelectedPlaceCalloutLayout | null>(null);
  const safeCenter = useMemo(
    () => coerceSafeMapCenter(center),
    [center.lat, center.lng],
  );
  const routeCollection = useMemo(
    () =>
      buildRouteFeatureCollection(
        days,
        places,
        selectedDay,
        selectedRouteDay ?? selectedPlace?.day ?? null,
      ),
    [days, places, selectedDay, selectedPlace?.day, selectedRouteDay],
  );
  const hotelHub = useMemo(
    () => deriveHotelHub(hotelBase),
    [hotelBase],
  );
  const hotelHubCollection = useMemo(
    () => buildHotelHubFeatureCollection(hotelHub),
    [hotelHub],
  );
  const hotelHubName = hotelHubCollection.features[0]?.properties?.name ?? null;
  const placeCollection = useMemo(
    () => buildPlaceFeatureCollection(places, selectedPlace?.id ?? null),
    [places, selectedPlace?.id],
  );
  const hasActiveRoute = useMemo(
    () => routeCollection.features.some((feature) => feature.properties.active),
    [routeCollection],
  );
  const selectedPlaceDay = useMemo(
    () => days.find((day) => day.day === selectedPlace?.day) ?? null,
    [days, selectedPlace?.day],
  );
  const selectedCalloutReason = useMemo(
    () => buildMapCalloutReason(selectedPlace, selectedPlaceDay),
    [selectedPlace, selectedPlaceDay],
  );
  const selectedCalloutEvidence = useMemo(
    () => buildMapCalloutEvidence(selectedPlace, selectedPlaceDay),
    [selectedPlace, selectedPlaceDay],
  );

  useEffect(() => {
    onSelectPlaceRef.current = onSelectPlace;
  }, [onSelectPlace]);

  useEffect(() => {
    onRegionFocusCompleteRef.current = onRegionFocusComplete;
  }, [onRegionFocusComplete]);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotionPreference = () => {
      prefersReducedMotionRef.current = motionQuery.matches;
    };

    updateMotionPreference();
    motionQuery.addEventListener("change", updateMotionPreference);

    return () => {
      motionQuery.removeEventListener("change", updateMotionPreference);
    };
  }, []);

  useEffect(() => {
    if (!mapboxToken || mapRef.current || !mapContainerRef.current) {
      return;
    }

    let isMounted = true;

    async function initializeMap() {
      const mapboxModule = await import("mapbox-gl");
      const mapboxgl = mapboxModule.default;

      if (!isMounted || !mapContainerRef.current || mapRef.current) {
        return;
      }

      mapboxgl.accessToken = mapboxToken;

      const map = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: "mapbox://styles/mapbox/standard",
        config: {
          basemap: getBasemapConfig(mode),
        },
        center: [safeCenter.lng, safeCenter.lat],
        zoom: getInitialCameraZoom(initialZoom, mode),
        pitch: getInitialCameraPitch(mode),
        bearing: getInitialCameraBearing(mode),
        projection: mode === "trip" ? "mercator" : "globe",
        antialias: true,
        attributionControl: false,
        maxPitch: 75,
      });

      map.addControl(
        new mapboxgl.NavigationControl({
          visualizePitch: true,
        }),
        "bottom-left",
      );

      map.addControl(
        new mapboxgl.AttributionControl({
          compact: true,
        }),
        "bottom-right",
      );

      mapRef.current = map;
      cleanupMapRuntimeGuardsRef.current = registerMapRuntimeGuards(map);

      map.once("load", () => {
        applyAtmosphere(map, mode);
        if (USE_SAFE_3D_FALLBACK) {
          addReliable3DBuildingsLayer(map);
        }
        ensureRouteLayers(map);
        ensurePlaceLayers(map);
        ensureHotelHubLayers(map);
        registerPlaceInteractions(map, prefersReducedMotionRef, onSelectPlaceRef);
        map.resize();
        if (isMounted) {
          setMapReady(true);
        }
      });

      requestAnimationFrame(() => {
        map.resize();
      });
    }

    initializeMap().catch((error: unknown) => {
      if (!isMounted) {
        return;
      }

      console.warn(
        "[TripCanvas map] Map initialization failed.",
        redactMapboxAccessToken(getUnknownErrorMessage(error)),
      );
    });

    return () => {
      isMounted = false;
      if (selectedPulseFrameRef.current !== null) {
        cancelAnimationFrame(selectedPulseFrameRef.current);
        selectedPulseFrameRef.current = null;
      }
      if (routeDashFrameRef.current !== null) {
        cancelAnimationFrame(routeDashFrameRef.current);
        routeDashFrameRef.current = null;
      }
      cleanupMapRuntimeGuardsRef.current?.();
      cleanupMapRuntimeGuardsRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, [mapboxToken]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    map.setProjection(mode === "trip" ? "mercator" : "globe");
    applyAtmosphere(map, mode);

    if (mode === "globe" && places.length === 0) {
      const globeCamera = {
        center: [safeCenter.lng, safeCenter.lat] as [number, number],
        zoom: GLOBE_ZOOM,
        pitch: GLOBE_PITCH,
        bearing: GLOBE_BEARING,
      } satisfies Parameters<Map["jumpTo"]>[0];

      if (prefersReducedMotionRef.current) {
        map.jumpTo(globeCamera);
        return;
      }

      map.easeTo({
        ...globeCamera,
        duration: 900,
        essential: false,
      });
    }
  }, [mapReady, mode, places.length, safeCenter.lat, safeCenter.lng]);

  useEffect(() => {
    if (!mapReady || !mapRef.current || mode !== "globe" || places.length > 0) {
      if (autoRotateFrameRef.current !== null) {
        cancelAnimationFrame(autoRotateFrameRef.current);
        autoRotateFrameRef.current = null;
      }
      return;
    }

    if (prefersReducedMotionRef.current) {
      return;
    }

    const map = mapRef.current;
    const rotate = () => {
      map.setBearing((map.getBearing() + GLOBE_ROTATION_SPEED) % 360);
      autoRotateFrameRef.current = requestAnimationFrame(rotate);
    };

    autoRotateFrameRef.current = requestAnimationFrame(rotate);

    return () => {
      if (autoRotateFrameRef.current !== null) {
        cancelAnimationFrame(autoRotateFrameRef.current);
        autoRotateFrameRef.current = null;
      }
    };
  }, [mapReady, mode, places.length]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    ensureRouteLayers(map);

    const source = map.getSource(ROUTE_SOURCE_ID);
    if (source && "setData" in source) {
      (source as GeoJSONSource).setData(routeCollection);
    }
  }, [mapReady, routeCollection]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    ensurePlaceLayers(map);
    updatePlaceSource(map, placeCollection);
  }, [mapReady, placeCollection]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    ensureHotelHubLayers(map);
    updateHotelHubSource(map, hotelHubCollection);
  }, [hotelHubCollection, mapReady]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    ensurePlaceLayers(map);

    if (selectedPulseFrameRef.current !== null) {
      cancelAnimationFrame(selectedPulseFrameRef.current);
      selectedPulseFrameRef.current = null;
    }

    if (!selectedPlace || prefersReducedMotionRef.current) {
      if (map.getLayer(PLACE_SELECTED_PULSE_LAYER_ID)) {
        map.setPaintProperty(PLACE_SELECTED_PULSE_LAYER_ID, "circle-radius", 32);
        map.setPaintProperty(PLACE_SELECTED_PULSE_LAYER_ID, "circle-opacity", 0.2);
      }
      return;
    }

    const animatePulse = (timestamp: number) => {
      if (!map.getLayer(PLACE_SELECTED_PULSE_LAYER_ID)) {
        return;
      }

      const progress = (timestamp % 1400) / 1400;
      const radius = 28 + progress * 18;
      const opacity = 0.26 - progress * 0.18;
      map.setPaintProperty(PLACE_SELECTED_PULSE_LAYER_ID, "circle-radius", radius);
      map.setPaintProperty(PLACE_SELECTED_PULSE_LAYER_ID, "circle-opacity", opacity);
      selectedPulseFrameRef.current = requestAnimationFrame(animatePulse);
    };

    selectedPulseFrameRef.current = requestAnimationFrame(animatePulse);

    return () => {
      if (selectedPulseFrameRef.current !== null) {
        cancelAnimationFrame(selectedPulseFrameRef.current);
        selectedPulseFrameRef.current = null;
      }
    };
  }, [mapReady, selectedPlace?.id]);

  useEffect(() => {
    if (!mapReady || !mapRef.current) {
      return;
    }

    const map = mapRef.current;
    ensureRouteLayers(map);

    if (routeDashFrameRef.current !== null) {
      cancelAnimationFrame(routeDashFrameRef.current);
      routeDashFrameRef.current = null;
    }

    if (!hasActiveRoute || prefersReducedMotionRef.current) {
      if (map.getLayer(ROUTE_ACTIVE_DASH_LAYER_ID)) {
        map.setPaintProperty(
          ROUTE_ACTIVE_DASH_LAYER_ID,
          "line-dasharray",
          ROUTE_DASH_SEQUENCE[0],
        );
      }
      return;
    }

    let step = -1;
    const animateRouteDash = (timestamp: number) => {
      if (!map.getLayer(ROUTE_ACTIVE_DASH_LAYER_ID)) {
        return;
      }

      const nextStep = Math.floor((timestamp / 80) % ROUTE_DASH_SEQUENCE.length);
      if (nextStep !== step) {
        map.setPaintProperty(
          ROUTE_ACTIVE_DASH_LAYER_ID,
          "line-dasharray",
          ROUTE_DASH_SEQUENCE[nextStep],
        );
        step = nextStep;
      }

      routeDashFrameRef.current = requestAnimationFrame(animateRouteDash);
    };

    routeDashFrameRef.current = requestAnimationFrame(animateRouteDash);

    return () => {
      if (routeDashFrameRef.current !== null) {
        cancelAnimationFrame(routeDashFrameRef.current);
        routeDashFrameRef.current = null;
      }
    };
  }, [hasActiveRoute, mapReady]);

  useEffect(() => {
    if (
      mode !== "trip" ||
      !mapReady ||
      !mapRef.current ||
      !selectedPlace ||
      !isValidLngLat(selectedPlace.lng, selectedPlace.lat)
    ) {
      if (!selectedPlace) {
        previousFlyToPlaceIdRef.current = null;
      }
      return;
    }

    if (previousFlyToPlaceIdRef.current === selectedPlace.id) {
      return;
    }

    previousFlyToPlaceIdRef.current = selectedPlace.id;
    const selectedCamera = {
      center: [selectedPlace.lng, selectedPlace.lat] as [number, number],
      zoom: getSelectedPlaceZoom(initialZoom),
      pitch: SELECTED_PLACE_PITCH,
      bearing: SELECTED_PLACE_BEARING,
    } satisfies Parameters<Map["jumpTo"]>[0];

    if (prefersReducedMotionRef.current) {
      mapRef.current.jumpTo(selectedCamera);
      return;
    }

    mapRef.current.flyTo({
      ...selectedCamera,
      offset: getSelectedPlaceOffset(),
      duration: 1400,
      essential: false,
    });
  }, [initialZoom, mapReady, mode, selectedPlace]);

  useEffect(() => {
    if (
      !mapReady ||
      !mapRef.current ||
      mode !== "trip" ||
      !selectedPlace ||
      !isValidLngLat(selectedPlace.lng, selectedPlace.lat)
    ) {
      setSelectedCalloutLayout(null);
      return;
    }

    const map = mapRef.current;
    const updateCallout = () => {
      const point = map.project([selectedPlace.lng, selectedPlace.lat]);
      const width = window.innerWidth < 640 ? 224 : 272;
      const height = window.innerWidth < 640 ? 126 : 132;
      const position = getMapCalloutPosition({
        marker: point,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight,
        },
        callout: {
          width,
          height,
        },
        margin: window.innerWidth < 768 ? 14 : 24,
        verticalGap: window.innerWidth < 640 ? 18 : 26,
      });

      setSelectedCalloutLayout({
        ...position,
        width,
        height,
        markerY: Math.round(point.y),
      });
    };

    updateCallout();
    map.on("move", updateCallout);
    map.on("resize", updateCallout);
    window.addEventListener("resize", updateCallout);

    return () => {
      map.off("move", updateCallout);
      map.off("resize", updateCallout);
      window.removeEventListener("resize", updateCallout);
    };
  }, [mapReady, mode, selectedPlace]);

  useEffect(() => {
    if (!mapReady || !mapRef.current || mode !== "extracting" || places.length === 0) {
      return;
    }

    const bounds = getPlacesBounds(places);
    if (!bounds) {
      return;
    }

    const signature = places
      .map((place) => `${place.id}:${place.lng.toFixed(4)},${place.lat.toFixed(4)}`)
      .join("|");

    if (focusedPlaceSignatureRef.current === signature) {
      return;
    }

    focusedPlaceSignatureRef.current = signature;
    previousFlyToPlaceIdRef.current = null;

    const map = mapRef.current;
    const complete = () => {
      map.off("moveend", complete);
      onRegionFocusCompleteRef.current?.();
    };
    const padding = getRegionFocusPadding();

    if (prefersReducedMotionRef.current) {
      map.fitBounds(bounds, {
        padding,
        maxZoom: 12.8,
        duration: 0,
      });
      window.setTimeout(() => onRegionFocusCompleteRef.current?.(), 0);
      return;
    }

    map.once("moveend", complete);
    map.fitBounds(bounds, {
      padding,
      maxZoom: 12.8,
      duration: 2200,
      essential: false,
    });
  }, [mapReady, mode, places]);

  return (
    <>
      <div className="absolute inset-0 h-screen w-screen">
        <div
          ref={mapContainerRef}
          data-trip-map-container
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
          }}
        />
      </div>
      <div className="tc-map-vignette pointer-events-none absolute inset-0" />
      {hotelHubName ? (
        <div className="pointer-events-none absolute left-1/2 top-5 z-10 hidden -translate-x-1/2 rounded-full border border-amber-200/30 bg-slate-950/72 px-4 py-2 text-xs font-black uppercase tracking-[0.18em] text-amber-100 shadow-2xl shadow-black/30 backdrop-blur-xl md:block">
          Base near {hotelHubName}
        </div>
      ) : null}
      {selectedPlace && selectedCalloutLayout ? (
        <div
          data-testid="selected-place-map-callout"
          className="pointer-events-none absolute z-20 rounded-lg border border-cyan-100/55 bg-slate-950/88 p-3 text-slate-50 shadow-2xl shadow-slate-950/35 backdrop-blur-xl"
          style={{
            left: selectedCalloutLayout.left,
            top: selectedCalloutLayout.top,
            width: selectedCalloutLayout.width,
            height: selectedCalloutLayout.height,
          }}
        >
          <span
            className={`absolute h-3 w-3 rotate-45 border-cyan-100/55 bg-slate-950/88 ${
              selectedCalloutLayout.top > selectedCalloutLayout.markerY
                ? "-top-1.5 border-l border-t"
                : "-bottom-1.5 border-b border-r"
            }`}
            style={{
              left: Math.min(
                Math.max(selectedCalloutLayout.anchorX - 6, 18),
                selectedCalloutLayout.width - 24,
              ),
            }}
          />
          <div className="relative space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-black text-white">
                  {selectedPlace.name}
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  <span className="rounded-full bg-cyan-300/18 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-cyan-100">
                    Day {selectedPlace.day}
                  </span>
                  <span className="rounded-full bg-amber-200/18 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-amber-100">
                    {selectedPlace.category}
                  </span>
                </div>
              </div>
              <span className="rounded-full border border-amber-100/45 bg-amber-200/18 px-2 py-1 text-[10px] font-black uppercase tracking-[0.14em] text-amber-100">
                Chosen
              </span>
            </div>
            <p
              className="text-[11px] font-semibold leading-snug text-slate-100"
              style={{
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: 3,
                overflow: "hidden",
              }}
            >
              {selectedCalloutReason}
            </p>
            <p className="hidden text-[10px] font-semibold leading-snug text-cyan-100/82 sm:block">
              {selectedCalloutEvidence}
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}

function deriveHotelHub(hotelBase?: TripHotelBase) {
  if (!hotelBase) {
    return null;
  }

  const selectedHotel =
    hotelBase.hotelCandidates.find((hotel) => hotel.id === hotelBase.selectedHotelId) ?? null;
  if (
    selectedHotel &&
    typeof selectedHotel.lng === "number" &&
    typeof selectedHotel.lat === "number" &&
    isValidLngLat(selectedHotel.lng, selectedHotel.lat)
  ) {
    return {
      name: selectedHotel.name || hotelBase.selectedHotelName,
      lng: selectedHotel.lng,
      lat: selectedHotel.lat,
      kind: "hotel" as const,
    };
  }

  const selectedBase =
    hotelBase.baseAreas.find((base) => base.id === hotelBase.selectedBaseId) ?? null;
  if (
    selectedBase?.center &&
    isValidLngLat(selectedBase.center.lng, selectedBase.center.lat)
  ) {
    return {
      name: selectedBase.name || hotelBase.selectedBaseName,
      lng: selectedBase.center.lng,
      lat: selectedBase.center.lat,
      kind: "base" as const,
    };
  }

  return null;
}

function buildMapCalloutReason(place: TripPlace | null, day: TripDay | null) {
  if (!place) {
    return "";
  }

  return truncateMapText(
    place.plannerSummary ||
      place.summary ||
      place.dayPlanText ||
      day?.summary ||
      "The planner selected this stop from the extracted Reel signals.",
    116,
  );
}

function buildMapCalloutEvidence(place: TripPlace | null, day: TripDay | null) {
  if (!place) {
    return "";
  }

  if (place.evidenceQuote) {
    return truncateMapText(`Reel evidence: "${place.evidenceQuote}"`, 108);
  }

  if (typeof place.confidence === "number") {
    return `${Math.round(place.confidence * 100)}% extraction confidence.`;
  }

  if (place.dayPlanText) {
    return truncateMapText(place.dayPlanText, 108);
  }

  return truncateMapText(day?.weatherStrategy || "Open the agent panel for the full rationale.", 108);
}

function truncateMapText(value: string, maxLength: number) {
  const normalized = value.replace(/\s+/g, " ").trim();

  if (normalized.length <= maxLength) {
    return normalized;
  }

  return `${normalized.slice(0, Math.max(0, maxLength - 1)).trim()}...`;
}

function registerMapRuntimeGuards(map: Map) {
  const handleMapError = (event: MapEventOf<"error">) => {
    const message = redactMapboxAccessToken(getUnknownErrorMessage(event.error));

    if (isExpectedMapboxRuntimeNoise(message)) {
      return;
    }

    console.warn("[TripCanvas map]", message || "Mapbox emitted an error event.");
  };

  const handleWebGlContextLost = (event: MapEventOf<"webglcontextlost">) => {
    event.originalEvent?.preventDefault();
  };

  const handleCanvasRuntimeEvent = (event: Event) => {
    if (event.type === "webglcontextlost") {
      event.preventDefault();
    }

    event.stopPropagation();
  };

  const canvas = map.getCanvas();
  map.on("error", handleMapError);
  map.on("webglcontextlost", handleWebGlContextLost);
  canvas.addEventListener("error", handleCanvasRuntimeEvent, true);
  canvas.addEventListener("webglcontextlost", handleCanvasRuntimeEvent, false);

  return () => {
    map.off("error", handleMapError);
    map.off("webglcontextlost", handleWebGlContextLost);
    canvas.removeEventListener("error", handleCanvasRuntimeEvent, true);
    canvas.removeEventListener("webglcontextlost", handleCanvasRuntimeEvent, false);
  };
}

function getUnknownErrorMessage(value: unknown) {
  if (!value) {
    return "";
  }

  if (value instanceof Error) {
    return value.message;
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof Event !== "undefined" && value instanceof Event) {
    return `${value.type || "unknown"} event`;
  }

  if (typeof value === "object" && "message" in value) {
    const message = (value as { message?: unknown }).message;
    if (typeof message === "string") {
      return message;
    }
  }

  return String(value);
}

function redactMapboxAccessToken(message: string) {
  return message.replace(/access_token=[^&\s)]+/g, "access_token=[redacted]");
}

function isExpectedMapboxRuntimeNoise(message: string) {
  return [
    "e.json.meshes is not iterable",
    "Failed to evaluate expression",
    "Cutoff is currently disabled on terrain",
  ].some((pattern) => message.includes(pattern));
}

function applyAtmosphere(map: Map, mode: TripMapMode) {
  try {
    if (mode === "trip") {
      map.setFog({
        color: "rgb(232, 242, 248)",
        "high-color": "rgb(188, 219, 235)",
        "horizon-blend": 0.08,
        "space-color": "rgb(246, 251, 255)",
        "star-intensity": 0,
      });
      return;
    }

    map.setFog({
      color: "rgb(15, 23, 42)",
      "high-color": "rgb(13, 148, 136)",
      "horizon-blend": 0.16,
      "space-color": "rgb(2, 6, 23)",
      "star-intensity": 0.38,
    });
  } catch {
    // Some Mapbox styles can reject fog options; the base map should still render.
  }
}

function getBasemapConfig(mode: TripMapMode) {
  if (mode === "trip") {
    return STANDARD_ARCHITECTURAL_BASEMAP_CONFIG;
  }

  return {
    ...STANDARD_ARCHITECTURAL_BASEMAP_CONFIG,
    lightPreset: "night",
    show3dBuildings: false,
    show3dFacades: false,
    show3dLandmarks: false,
    show3dTrees: false,
    showRoadLabels: false,
    showTransitLabels: false,
    showPedestrianRoads: false,
  };
}

function addReliable3DBuildingsLayer(map: Map) {
  if (map.getLayer(RELIABLE_BUILDINGS_LAYER_ID)) {
    return;
  }

  const hasCompositeSource = Boolean(map.getStyle().sources?.composite);
  if (!hasCompositeSource) {
    return;
  }

  const buildingLayer: AnyLayer = {
    id: RELIABLE_BUILDINGS_LAYER_ID,
    source: "composite",
    "source-layer": "building",
    filter: ["==", ["get", "extrude"], "true"],
    type: "fill-extrusion",
    minzoom: 13.4,
    slot: "middle",
    paint: {
      "fill-extrusion-color": [
        "interpolate",
        ["linear"],
        ["get", "height"],
        0,
        "#f4efe6",
        90,
        "#e8dfcf",
        180,
        "#d5c3a8",
        280,
        "#b9d7e8",
      ],
      "fill-extrusion-height": [
        "interpolate",
        ["linear"],
        ["zoom"],
        13.4,
        0,
        15.4,
        ["coalesce", ["get", "height"], 12],
      ],
      "fill-extrusion-base": [
        "interpolate",
        ["linear"],
        ["zoom"],
        13.4,
        0,
        15.4,
        ["coalesce", ["get", "min_height"], 0],
      ],
      "fill-extrusion-opacity": 0.74,
      "fill-extrusion-vertical-gradient": true,
      "fill-extrusion-emissive-strength": 0.05,
    },
  };

  try {
    map.addLayer(buildingLayer);
  } catch {
    // Some Mapbox Standard imports may hide the raw building source; the map stays usable.
  }
}

function ensureRouteLayers(map: Map) {
  if (!map.getSource(ROUTE_SOURCE_ID)) {
    map.addSource(ROUTE_SOURCE_ID, {
      type: "geojson",
      data: EMPTY_ROUTE_COLLECTION,
      lineMetrics: true,
    });
  }

  if (!map.getLayer(ROUTE_CASING_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_CASING_LAYER_ID,
      type: "line",
      source: ROUTE_SOURCE_ID,
      slot: "top",
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": [
          "case",
          ["boolean", ["get", "active"], false],
          "rgba(15, 23, 42, 0.74)",
          "rgba(15, 23, 42, 0.3)",
        ],
        "line-width": buildActiveAwareLineWidth({
          zoomStops: [
            [10, 9, 3.5],
            [14, 16, 6],
            [16, 21, 8],
          ],
        }),
        "line-opacity": [
          "case",
          ["boolean", ["get", "active"], false],
          0.76,
          0.2,
        ],
        "line-blur": 0.7,
        "line-emissive-strength": 0.2,
      },
    });
  }

  if (!map.getLayer(ROUTE_UNDERLAY_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_UNDERLAY_LAYER_ID,
      type: "line",
      source: ROUTE_SOURCE_ID,
      slot: "top",
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": [
          "case",
          ["boolean", ["get", "active"], false],
          "rgba(34, 211, 238, 0.7)",
          "rgba(20, 184, 166, 0.2)",
        ],
        "line-width": buildActiveAwareLineWidth({
          zoomStops: [
            [10, 6.4, 2.5],
            [14, 11.5, 4.2],
            [16, 15, 6],
          ],
        }),
        "line-opacity": [
          "case",
          ["boolean", ["get", "active"], false],
          0.86,
          0.26,
        ],
        "line-blur": 1.2,
        "line-emissive-strength": 0.5,
      },
    });
  }

  if (!map.getLayer(ROUTE_ACTIVE_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_ACTIVE_LAYER_ID,
      type: "line",
      source: ROUTE_SOURCE_ID,
      slot: "top",
      filter: ["==", ["get", "active"], true],
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": "#22d3ee",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 4.8, 14, 8, 16, 10],
        "line-opacity": 0.96,
        "line-emissive-strength": 0.78,
      },
    });
  }

  if (!map.getLayer(ROUTE_ACTIVE_DASH_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_ACTIVE_DASH_LAYER_ID,
      type: "line",
      source: ROUTE_SOURCE_ID,
      slot: "top",
      filter: ["==", ["get", "active"], true],
      layout: {
        "line-cap": "round",
        "line-join": "round",
      },
      paint: {
        "line-color": "#fef3c7",
        "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1.8, 14, 3, 16, 4],
        "line-opacity": 0.92,
        "line-dasharray": ROUTE_DASH_SEQUENCE[0],
        "line-emissive-strength": 0.9,
      },
    });
  }
}

function ensurePlaceLayers(map: Map) {
  if (!map.getSource(PLACE_SOURCE_ID)) {
    map.addSource(PLACE_SOURCE_ID, {
      type: "geojson",
      data: EMPTY_PLACE_COLLECTION,
      cluster: true,
      clusterRadius: 80,
      clusterMaxZoom: 11,
      clusterMinPoints: 2,
    });
  }

  const clusterLayer: AnyLayer = {
    id: PLACE_CLUSTER_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": [
        "step",
        ["get", "point_count"],
        "#fde68a",
        4,
        "#facc15",
        8,
        "#fb923c",
      ],
      "circle-radius": ["step", ["get", "point_count"], 23, 4, 28, 8, 34],
      "circle-opacity": 0.94,
      "circle-stroke-color": "rgba(15, 23, 42, 0.76)",
      "circle-stroke-width": 2,
      "circle-blur": 0.02,
      "circle-emissive-strength": 0.18,
    },
  };

  const clusterCountLayer: AnyLayer = {
    id: PLACE_CLUSTER_COUNT_LAYER_ID,
    type: "symbol",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["DIN Offc Pro Bold", "Arial Unicode MS Bold"],
      "text-size": 13,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: {
      "text-color": "rgba(3, 7, 18, 0.92)",
      "text-emissive-strength": 0.25,
    },
  };

  const clusterHitboxLayer: AnyLayer = {
    id: PLACE_CLUSTER_HITBOX_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": "#ffffff",
      "circle-radius": ["step", ["get", "point_count"], 31, 4, 37, 8, 44],
      "circle-opacity": 0.01,
    },
  };

  const placeSelectedPulseLayer: AnyLayer = {
    id: PLACE_SELECTED_PULSE_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: [
      "all",
      ["!", ["has", "point_count"]],
      ["==", ["get", "selected"], true],
    ],
    paint: {
      "circle-color": "#22d3ee",
      "circle-radius": 32,
      "circle-opacity": 0.2,
      "circle-stroke-color": "#fef3c7",
      "circle-stroke-width": 2,
      "circle-blur": 0.28,
      "circle-emissive-strength": 0.58,
    },
  };

  const placeHaloLayer: AnyLayer = {
    id: PLACE_HALO_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": placeColorExpression(),
      "circle-radius": [
        "case",
        ["boolean", ["get", "selected"], false],
        34,
        ["boolean", ["get", "muted"], false],
        9,
        18,
      ],
      "circle-opacity": [
        "case",
        ["boolean", ["get", "selected"], false],
        0.54,
        ["boolean", ["get", "muted"], false],
        0.04,
        0.2,
      ],
      "circle-blur": 0.42,
      "circle-emissive-strength": 0.32,
    },
  };

  const placeDotLayer: AnyLayer = {
    id: PLACE_DOT_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": placeColorExpression(),
      "circle-radius": [
        "case",
        ["boolean", ["get", "selected"], false],
        15,
        ["boolean", ["get", "muted"], false],
        4.8,
        8.5,
      ],
      "circle-stroke-color": [
        "case",
        ["boolean", ["get", "selected"], false],
        "#fef3c7",
        ["boolean", ["get", "muted"], false],
        "rgba(255, 255, 255, 0.36)",
        "rgba(255, 255, 255, 0.96)",
      ],
      "circle-stroke-width": [
        "case",
        ["boolean", ["get", "selected"], false],
        6,
        ["boolean", ["get", "muted"], false],
        1.5,
        5,
      ],
      "circle-opacity": [
        "case",
        ["boolean", ["get", "selected"], false],
        1,
        ["boolean", ["get", "muted"], false],
        0.2,
        0.98,
      ],
      "circle-emissive-strength": 0.38,
    },
  };

  const placeGlyphLayer: AnyLayer = {
    id: PLACE_GLYPH_LAYER_ID,
    type: "symbol",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["!", ["has", "point_count"]],
    layout: {
      "text-field": ["get", "glyph"],
      "text-font": ["DIN Offc Pro Bold", "Arial Unicode MS Bold"],
      "text-size": [
        "case",
        ["boolean", ["get", "selected"], false],
        13,
        ["boolean", ["get", "muted"], false],
        8,
        10.5,
      ],
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: {
      "text-color": "rgba(3, 7, 18, 0.9)",
      "text-opacity": [
        "case",
        ["boolean", ["get", "selected"], false],
        1,
        ["boolean", ["get", "muted"], false],
        0.22,
        0.9,
      ],
      "text-emissive-strength": 0.18,
    },
  };

  const placeHitboxLayer: AnyLayer = {
    id: PLACE_HITBOX_LAYER_ID,
    type: "circle",
    source: PLACE_SOURCE_ID,
    slot: "top",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": "#ffffff",
      "circle-radius": 24,
      "circle-opacity": 0.01,
    },
  };

  [
    clusterLayer,
    clusterCountLayer,
    clusterHitboxLayer,
    placeSelectedPulseLayer,
    placeHaloLayer,
    placeDotLayer,
    placeGlyphLayer,
    placeHitboxLayer,
  ].forEach((layer) => {
    if (!map.getLayer(layer.id)) {
      map.addLayer(layer);
    }
  });
}

function ensureHotelHubLayers(map: Map) {
  if (!map.getSource(HOTEL_HUB_SOURCE_ID)) {
    map.addSource(HOTEL_HUB_SOURCE_ID, {
      type: "geojson",
      data: EMPTY_HOTEL_HUB_COLLECTION,
    });
  }

  const hotelHubHaloLayer: AnyLayer = {
    id: HOTEL_HUB_HALO_LAYER_ID,
    type: "circle",
    source: HOTEL_HUB_SOURCE_ID,
    slot: "top",
    paint: {
      "circle-color": "#22d3ee",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 28, 15, 48],
      "circle-opacity": 0.3,
      "circle-blur": 0.55,
      "circle-emissive-strength": 0.42,
    },
  };

  const hotelHubRingLayer: AnyLayer = {
    id: HOTEL_HUB_RING_LAYER_ID,
    type: "circle",
    source: HOTEL_HUB_SOURCE_ID,
    slot: "top",
    paint: {
      "circle-color": "rgba(15, 23, 42, 0.76)",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 17, 15, 24],
      "circle-stroke-color": "#fde68a",
      "circle-stroke-width": 5,
      "circle-opacity": 0.96,
      "circle-emissive-strength": 0.28,
    },
  };

  const hotelHubDotLayer: AnyLayer = {
    id: HOTEL_HUB_DOT_LAYER_ID,
    type: "circle",
    source: HOTEL_HUB_SOURCE_ID,
    slot: "top",
    paint: {
      "circle-color": "#67e8f9",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 9, 15, 13],
      "circle-stroke-color": "rgba(15, 23, 42, 0.94)",
      "circle-stroke-width": 3,
      "circle-opacity": 0.98,
      "circle-emissive-strength": 0.38,
    },
  };

  const hotelHubGlyphLayer: AnyLayer = {
    id: HOTEL_HUB_GLYPH_LAYER_ID,
    type: "symbol",
    source: HOTEL_HUB_SOURCE_ID,
    slot: "top",
    layout: {
      "text-field": ["get", "glyph"],
      "text-font": ["DIN Offc Pro Bold", "Arial Unicode MS Bold"],
      "text-size": 12,
      "text-allow-overlap": true,
      "text-ignore-placement": true,
    },
    paint: {
      "text-color": "rgba(3, 7, 18, 0.92)",
      "text-emissive-strength": 0.24,
    },
  };

  const hotelHubLabelLayer: AnyLayer = {
    id: HOTEL_HUB_LABEL_LAYER_ID,
    type: "symbol",
    source: HOTEL_HUB_SOURCE_ID,
    slot: "top",
    layout: {
      "text-field": ["concat", "BASE  ", ["get", "name"]],
      "text-font": ["DIN Offc Pro Bold", "Arial Unicode MS Bold"],
      "text-size": 11,
      "text-offset": [0, -3.1],
      "text-anchor": "bottom",
      "text-allow-overlap": false,
      "text-ignore-placement": false,
      "text-max-width": 16,
    },
    paint: {
      "text-color": "#fef3c7",
      "text-halo-color": "rgba(3, 7, 18, 0.9)",
      "text-halo-width": 1.8,
      "text-emissive-strength": 0.26,
    },
  };

  [
    hotelHubHaloLayer,
    hotelHubRingLayer,
    hotelHubDotLayer,
    hotelHubGlyphLayer,
    hotelHubLabelLayer,
  ].forEach((layer) => {
    if (!map.getLayer(layer.id)) {
      map.addLayer(layer);
    }
  });
}

function updatePlaceSource(map: Map, placeCollection: PlaceFeatureCollection) {
  const source = map.getSource(PLACE_SOURCE_ID);
  if (source && "setData" in source) {
    (source as GeoJSONSource).setData(placeCollection);
  }
}

function updateHotelHubSource(map: Map, hotelHubCollection: HotelHubFeatureCollection) {
  const source = map.getSource(HOTEL_HUB_SOURCE_ID);
  if (source && "setData" in source) {
    (source as GeoJSONSource).setData(hotelHubCollection);
  }
}

function buildRouteFeatureCollection(
  days: TripDay[],
  places: TripPlace[],
  selectedDay: DayFilter,
  selectedRouteDay: TripDay["day"] | null,
): RouteFeatureCollection {
  const routeDays =
    selectedDay === "all" ? days : days.filter((day) => day.day === selectedDay);
  const activeRouteDay = selectedDay === "all" ? selectedRouteDay : selectedDay;
  const placeById = new globalThis.Map<string, TripPlace>();
  places.forEach((place) => {
    placeById.set(place.id, place);
  });
  const features: RouteFeatureCollection["features"] = [];

  routeDays.forEach((day) => {
    const coordinates =
      day.route?.coordinates && day.route.coordinates.length >= 2
        ? day.route.coordinates
        : buildFallbackRouteCoordinates(day, placeById);

    if (coordinates.length < 2) {
      return;
    }

    features.push({
      type: "Feature",
      id: `day-${day.day}`,
      properties: {
        day: day.day,
        active: activeRouteDay !== null && day.day === activeRouteDay,
      },
      geometry: {
        type: "LineString",
        coordinates,
      },
    });
  });

  return {
    type: "FeatureCollection",
    features,
  };
}

function buildFallbackRouteCoordinates(
  day: TripDay,
  placeById: ReadonlyMap<string, TripPlace>,
): [number, number][] {
  return day.placeIds.flatMap((placeId) => {
    const place = placeById.get(placeId);
    if (!place || !isValidLngLat(place.lng, place.lat)) {
      return [];
    }

    return [[place.lng, place.lat] as [number, number]];
  });
}

function buildPlaceFeatureCollection(
  places: TripPlace[],
  selectedPlaceId: string | null,
): PlaceFeatureCollection {
  return {
    type: "FeatureCollection",
    features: places.flatMap((place) => {
      if (!isValidLngLat(place.lng, place.lat)) {
        return [];
      }

      return [
        {
          type: "Feature",
          id: place.id,
          properties: {
            placeId: place.id,
            name: place.name,
            category: place.category,
            day: place.day,
            glyph: getMarkerGlyph(place.category),
            selected: place.id === selectedPlaceId,
            muted: selectedPlaceId !== null && place.id !== selectedPlaceId,
          },
          geometry: {
            type: "Point",
            coordinates: [place.lng, place.lat],
          },
        },
      ];
    }),
  };
}

function buildHotelHubFeatureCollection(
  hotelHub: ReturnType<typeof deriveHotelHub>,
): HotelHubFeatureCollection {
  if (!hotelHub) {
    return EMPTY_HOTEL_HUB_COLLECTION;
  }

  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "selected-hotel-base",
        properties: {
          name: hotelHub.name,
          glyph: hotelHub.kind === "hotel" ? "H" : "B",
          kind: hotelHub.kind,
        },
        geometry: {
          type: "Point",
          coordinates: [hotelHub.lng, hotelHub.lat],
        },
      },
    ],
  };
}

function registerPlaceInteractions(
  map: Map,
  prefersReducedMotionRef: { current: boolean },
  onSelectPlaceRef: { current: (placeId: string) => void },
) {
  map.on("click", PLACE_HITBOX_LAYER_ID, (event: MapLayerMouseEvent) => {
    const placeId = event.features?.[0]?.properties?.placeId;
    if (typeof placeId !== "string" || placeId.length === 0) {
      return;
    }

    event.preventDefault();
    onSelectPlaceRef.current(placeId);
  });

  map.on("click", PLACE_CLUSTER_HITBOX_LAYER_ID, (event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    const clusterId = Number(feature?.properties?.cluster_id);
    const coordinates = feature ? getPointCoordinates(feature) : null;
    const source = map.getSource(PLACE_SOURCE_ID);

    if (
      !Number.isFinite(clusterId) ||
      !coordinates ||
      !source ||
      !("getClusterExpansionZoom" in source)
    ) {
      return;
    }

    event.preventDefault();
    (source as GeoJSONSource).getClusterExpansionZoom(clusterId, (error, zoom) => {
      if (error || zoom == null) {
        return;
      }

      const clusterCamera = {
        center: coordinates,
        zoom: Math.min(zoom + 0.35, 14.6),
        pitch: STANDARD_DAY_PITCH,
        bearing: STANDARD_DAY_BEARING,
      } satisfies Parameters<Map["jumpTo"]>[0];

      if (prefersReducedMotionRef.current) {
        map.jumpTo(clusterCamera);
        return;
      }

      map.easeTo({
        ...clusterCamera,
        duration: 900,
        essential: false,
      });
    });
  });

  [PLACE_HITBOX_LAYER_ID, PLACE_CLUSTER_HITBOX_LAYER_ID].forEach((layerId) => {
    map.on("mouseenter", layerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });

    map.on("mouseleave", layerId, () => {
      map.getCanvas().style.cursor = "";
    });
  });
}

function placeColorExpression(): ExpressionSpecification {
  return [
    "case",
    ["boolean", ["get", "selected"], false],
    "#fde68a",
    [
      "match",
      ["get", "category"],
      ["hotel", "transport", "station"],
      "#67e8f9",
      ["restaurant", "market"],
      "#fb923c",
      ["temple", "shrine", "landmark", "attraction"],
      "#fde68a",
      "#facc15",
    ],
  ] as ExpressionSpecification;
}

function getPointCoordinates(feature: { geometry?: GeoJSON.Geometry | null }) {
  if (feature.geometry?.type !== "Point") {
    return null;
  }

  const [lng, lat] = feature.geometry.coordinates;
  return isValidLngLat(lng, lat) ? ([lng, lat] as [number, number]) : null;
}

function isValidLngLat(lng: unknown, lat: unknown) {
  return isValidLngLatValue(lng, lat);
}

function getInitialCameraZoom(initialZoom: number, mode: TripMapMode) {
  if (mode !== "trip") {
    return GLOBE_ZOOM;
  }

  return Math.min(Math.max(initialZoom + 0.85, 11.8), 13.2);
}

function getInitialCameraPitch(mode: TripMapMode) {
  return mode === "trip" ? STANDARD_DAY_PITCH : GLOBE_PITCH;
}

function getInitialCameraBearing(mode: TripMapMode) {
  return mode === "trip" ? STANDARD_DAY_BEARING : GLOBE_BEARING;
}

function getSelectedPlaceZoom(initialZoom: number) {
  return Math.min(Math.max(initialZoom + 4.25, 15.4), 16.4);
}

function getPlacesBounds(places: TripPlace[]) {
  const validPlaces = places.filter((place) => isValidLngLat(place.lng, place.lat));
  if (validPlaces.length === 0) {
    return null;
  }

  const lngs = validPlaces.map((place) => place.lng);
  const lats = validPlaces.map((place) => place.lat);
  let minLng = Math.min(...lngs);
  let maxLng = Math.max(...lngs);
  let minLat = Math.min(...lats);
  let maxLat = Math.max(...lats);

  if (minLng === maxLng) {
    minLng -= 0.018;
    maxLng += 0.018;
  }

  if (minLat === maxLat) {
    minLat -= 0.018;
    maxLat += 0.018;
  }

  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ] as [[number, number], [number, number]];
}

function getRegionFocusPadding() {
  if (typeof window === "undefined") {
    return 120;
  }

  if (window.innerWidth < 768) {
    return {
      top: 144,
      right: 24,
      bottom: 124,
      left: 24,
    };
  }

  return {
    top: 84,
    right: 390,
    bottom: 116,
    left: 350,
  };
}

function getSelectedPlaceOffset(): [number, number] {
  if (typeof window === "undefined") {
    return [0, 0];
  }

  if (window.innerWidth < 1024) {
    return [0, -96];
  }

  return [0, 0];
}

function getMarkerGlyph(category: TripPlace["category"]) {
  const glyphByCategory: Partial<Record<TripPlace["category"], string>> = {
    landmark: "L",
    crossing: "X",
    temple: "T",
    shrine: "S",
    market: "M",
    restaurant: "R",
    hotel: "H",
    attraction: "A",
    transport: "T",
    activity: "A",
    station: "S",
  };

  return glyphByCategory[category] ?? "P";
}
