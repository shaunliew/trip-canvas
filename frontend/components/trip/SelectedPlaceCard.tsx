import type { TripDay, TripPlace } from "@/lib/trip/types";

type SelectedPlaceCardProps = {
  place: TripPlace | null;
  days?: TripDay[];
  locked?: boolean;
  onToggleLock?: (placeId: string) => void;
  onViewIntel?: () => void;
};

export function SelectedPlaceCard({
  place,
  days = [],
  locked = false,
  onToggleLock,
  onViewIntel,
}: SelectedPlaceCardProps) {
  if (!place) {
    return null;
  }

  const day = days.find((candidate) => candidate.day === place.day) ?? null;
  const rationale = buildRationaleText(place, day);
  const evidence = buildEvidenceText(place);
  const travelFit = buildTravelFitText(place, day);

  return (
    <section className="absolute bottom-[110px] left-3 right-3 z-10 max-w-[360px] rounded-xl border border-amber-100/15 bg-[#101821]/86 p-3 shadow-2xl shadow-black/35 backdrop-blur-xl md:left-4 md:right-auto lg:hidden">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] font-black uppercase tracking-[0.22em] text-amber-200">
            Why this stop
          </p>
          <h2 className="mt-1 truncate text-lg font-black leading-6 tracking-tight text-white">
            {place.name}
          </h2>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <Pill>Day {place.day}</Pill>
          <Pill>{place.category}</Pill>
          {locked ? <Pill>Locked</Pill> : null}
        </div>
      </div>

      <p className="mt-2 line-clamp-1 text-xs font-semibold leading-5 text-slate-200 sm:line-clamp-2">
        {rationale}
      </p>

      <div className="mt-2 hidden gap-2 sm:grid md:grid-cols-2">
        <DecisionSnippet label="Evidence" value={evidence} />
        <DecisionSnippet label="Travel fit" value={travelFit} />
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {onViewIntel ? (
          <button
            type="button"
            onClick={onViewIntel}
            className="h-8 rounded-lg border border-amber-200/35 bg-amber-200/14 px-3 text-[11px] font-black uppercase tracking-[0.14em] text-amber-100 transition hover:bg-amber-200/22"
          >
            Why this
          </button>
        ) : null}
        {onToggleLock ? (
          <button
            type="button"
            onClick={() => onToggleLock(place.id)}
            className={[
              "h-8 rounded-lg border px-3 text-[11px] font-black uppercase tracking-[0.14em] transition",
              locked
                ? "border-teal-200/45 bg-teal-300/14 text-teal-100"
                : "border-white/10 bg-white/8 text-slate-200 hover:bg-white/12",
            ].join(" ")}
          >
            {locked ? "Stop locked" : "Lock stop"}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function DecisionSnippet({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-white/8 bg-white/6 px-2.5 py-2">
      <p className="text-[9px] font-black uppercase tracking-[0.16em] text-slate-500">
        {label}
      </p>
      <p className="mt-1 line-clamp-1 text-[11px] font-semibold leading-4 text-slate-300">
        {value}
      </p>
    </div>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/12 px-2.5 py-0.5 text-[10px] font-bold capitalize text-slate-100">
      {children}
    </span>
  );
}

function buildRationaleText(place: TripPlace, day: TripDay | null) {
  return truncateText(
    place.plannerSummary || place.summary || place.dayPlanText || day?.summary || "Mapped from the extracted Reel context.",
    180,
  );
}

function buildEvidenceText(place: TripPlace) {
  if (place.evidenceQuote) {
    return truncateText(place.evidenceQuote, 92);
  }

  if (typeof place.confidence === "number") {
    return `${Math.round(place.confidence * 100)}% extraction confidence.`;
  }

  return "No direct Reel quote returned.";
}

function buildTravelFitText(place: TripPlace, day: TripDay | null) {
  const text = [place.dayPlanText, place.plannerSummary, day?.summary, day?.weatherStrategy]
    .filter(Boolean)
    .join(" ");
  const tradeoff = splitSentences(text).find((sentence) => {
    const lower = sentence.toLowerCase();
    return ["long", "walk", "transit", "station", "weather", "rain", "route", "far"].some(
      (keyword) => lower.includes(keyword),
    );
  });

  return truncateText(tradeoff || place.address || "No explicit tradeoff returned.", 92);
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
