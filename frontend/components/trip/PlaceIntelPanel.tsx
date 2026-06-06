import { buildPlaceIntel } from "@/lib/trip/place-intel";
import {
  buildRoutePreview,
  getCategoryGlyph,
  splitItineraryTextSections,
} from "@/lib/trip/itinerary-ui";
import type { TripDay, TripPlace } from "@/lib/trip/types";

type PlaceIntelPanelProps = {
  place: TripPlace | null;
  days: TripDay[];
  places: TripPlace[];
  locked?: boolean;
  routePreviewActive?: boolean;
  onToggleLock?: (placeId: string) => void;
  onPreviewRoute?: (placeId: string) => void;
  onRequestRegenerateDay?: (day: number) => void;
};

export function PlaceIntelPanel({
  place,
  days,
  places,
  locked = false,
  routePreviewActive = false,
  onToggleLock,
  onPreviewRoute,
  onRequestRegenerateDay,
}: PlaceIntelPanelProps) {
  if (!place) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/8 px-4 py-5 text-sm font-semibold leading-6 text-slate-300">
        Select a map place to see its agent-curated travel details.
      </div>
    );
  }

  const intel = buildPlaceIntel(place, days);
  const day = days.find((candidate) => candidate.day === place.day) ?? null;
  const whatToDoSections = splitItineraryTextSections(buildWhatToDoText(place, day));
  const travelFit = buildTravelFitText(place, day, intel.howToGo);
  const routePreview = buildRoutePreview(place, days, places);
  const confidenceLabel =
    typeof place.confidence === "number" ? `${Math.round(place.confidence * 100)}%` : "Source";

  return (
    <div className="space-y-3">
      <header>
        <p className="text-[10px] font-black uppercase tracking-[0.22em] text-teal-200">
          Why this
        </p>
        <h2 className="mt-1 text-xl font-black leading-6 tracking-tight text-white">{place.name}</h2>
        <div className="mt-2 flex flex-wrap gap-1.5">
          <Pill>Day {place.day}</Pill>
          <Pill>{place.category}</Pill>
          <Pill>{confidenceLabel}</Pill>
        </div>
      </header>

      <div className="overflow-hidden rounded-lg border border-white/10 bg-gradient-to-br from-teal-300/14 via-white/8 to-amber-200/12 p-3">
        <p className="text-[9px] font-black uppercase tracking-[0.2em] text-slate-400">
          {intel.visual.label}
        </p>
        <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-200">{intel.visual.detail}</p>
      </div>

      <IntelSection title="Why chosen">
        <p>{intel.whyThisStop}</p>
      </IntelSection>

      <IntelSection title="What to do there">
        {whatToDoSections.length > 0 ? (
          <div className="space-y-2.5">
            {whatToDoSections.map((section) => (
              <div key={`${section.label}-${section.text.slice(0, 18)}`}>
                <p className="text-[10px] font-black uppercase tracking-[0.16em] text-amber-100">
                  {section.label}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-slate-200">{section.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p>The planner did not return a detailed activity note for this stop.</p>
        )}
      </IntelSection>

      <IntelSection title="Evidence">
        {place.evidenceQuote ? (
          <p>"{place.evidenceQuote}"</p>
        ) : (
          <p>No Reel evidence quote was returned.</p>
        )}
        <p className="mt-2 text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
          {intel.sourceLabel}
        </p>
        {place.sourceUrl ? (
          <a
            href={place.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-flex text-xs font-bold text-teal-100 underline decoration-teal-200/50 underline-offset-4"
          >
            View source
          </a>
        ) : null}
      </IntelSection>

      <IntelSection title="Travel fit">
        <p>{travelFit}</p>
        {day?.weatherStrategy ? (
          <p className="mt-2 text-slate-400">{day.weatherStrategy}</p>
        ) : null}
        <p className="mt-2 text-slate-400">{intel.howToGo}</p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Metric label="Best time" value={intel.bestTime} />
          <Metric label="Duration" value={intel.suggestedDuration} />
        </div>
        <button
          type="button"
          disabled={!onPreviewRoute || !routePreview}
          onClick={() => onPreviewRoute?.(place.id)}
          className="mt-2 inline-flex h-8 items-center rounded-lg border border-amber-200/35 bg-amber-200/15 px-3 text-[11px] font-black uppercase tracking-[0.14em] text-amber-100 transition hover:bg-amber-200/22 disabled:cursor-not-allowed disabled:opacity-45"
        >
          Preview route in map
        </button>
      </IntelSection>

      {routePreview ? (
        <RoutePreviewPanel active={routePreviewActive} preview={routePreview} />
      ) : null}

      {onToggleLock || onRequestRegenerateDay ? (
        <div className="grid gap-2">
          {onToggleLock ? (
            <button
              type="button"
              onClick={() => onToggleLock(place.id)}
              className={[
                "h-8 rounded-lg border px-3 text-[11px] font-black uppercase tracking-[0.12em] transition",
                locked
                  ? "border-teal-200/45 bg-teal-300/14 text-teal-100"
                  : "border-white/10 bg-white/8 text-slate-200 hover:bg-white/12",
              ].join(" ")}
            >
              {locked ? "Stop locked" : "Lock this stop"}
            </button>
          ) : null}
          {onRequestRegenerateDay ? (
            <button
              type="button"
              onClick={() => onRequestRegenerateDay(place.day)}
              className="h-8 rounded-lg border border-amber-200/35 bg-amber-200/14 px-3 text-[11px] font-black uppercase tracking-[0.12em] text-amber-100 transition hover:bg-amber-200/22"
            >
              Regenerate Day {place.day}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function IntelSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-white/10 bg-white/8 px-3 py-2.5 text-xs font-semibold leading-5 text-slate-300">
      <p className="mb-1.5 text-[9px] font-black uppercase tracking-[0.18em] text-slate-500">
        {title}
      </p>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/8 px-2.5 py-2">
      <p className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-xs font-black capitalize leading-4 text-slate-100">{value}</p>
    </div>
  );
}

function RoutePreviewPanel({
  active,
  preview,
}: {
  active: boolean;
  preview: NonNullable<ReturnType<typeof buildRoutePreview>>;
}) {
  return (
    <section
      data-testid="in-app-route-preview"
      className={[
        "rounded-lg border px-3 py-2.5 text-xs font-semibold leading-5",
        active
          ? "border-cyan-100/35 bg-cyan-300/10 text-slate-100"
          : "border-white/10 bg-white/8 text-slate-300",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] font-black uppercase tracking-[0.18em] text-cyan-100">
            In-app route
          </p>
          <p className="mt-1 text-sm font-black leading-5 text-white">
            Day {preview.day}: {preview.title}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-[10px] font-black text-slate-100">
          {preview.routeLabel}
        </span>
      </div>
      {preview.summary ? (
        <p className="mt-2 text-slate-300">{preview.summary}</p>
      ) : null}
      <ol className="mt-2 space-y-1.5">
        {preview.stops.map((stop, index) => (
          <li
            key={stop.id}
            className={[
              "grid grid-cols-[24px_1fr] items-center gap-2 rounded-lg border px-2 py-1.5",
              stop.selected
                ? "border-amber-200/45 bg-amber-200/12"
                : "border-white/8 bg-slate-950/28",
            ].join(" ")}
          >
            <span
              className={[
                "flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-black",
                stop.selected
                  ? "bg-amber-200 text-slate-950"
                  : "bg-white/10 text-slate-200",
              ].join(" ")}
            >
              {index + 1}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-xs font-black text-white">
                {stop.name}
              </span>
              <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
                {getCategoryGlyph(stop.category)} / {stop.category}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/12 px-2.5 py-1 text-[11px] font-bold capitalize text-slate-100">
      {children}
    </span>
  );
}

function buildWhatToDoText(place: TripPlace, day: TripDay | null) {
  if (place.dayPlanText) {
    return place.dayPlanText;
  }

  if (place.summary) {
    return place.summary;
  }

  if (day?.summary) {
    return day.summary;
  }

  return "";
}

function buildTravelFitText(place: TripPlace, day: TripDay | null, fallback: string) {
  const text = [place.plannerSummary, place.dayPlanText, day?.summary, day?.weatherStrategy]
    .filter(Boolean)
    .join(" ");
  const fit = splitSentences(text).find((sentence) => {
    const lower = sentence.toLowerCase();
    return ["tradeoff", "long", "walk", "transit", "station", "weather", "rain", "far", "route"].some(
      (keyword) => lower.includes(keyword),
    );
  });

  if (fit) {
    return fit;
  }

  if (fallback) {
    return fallback;
  }

  return `Planned on Day ${place.day}; no explicit route tradeoff was returned.`;
}

function splitSentences(text: string) {
  return text
    .split(/(?<=[.!?])\s+|;\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}
