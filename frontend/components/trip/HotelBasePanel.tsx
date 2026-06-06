import type { HotelPreferencePayload } from "@/lib/trip/backend-types";

export const HOTEL_BASE_CHIPS = [
  { id: "optimize_for_me", label: "Optimize for me" },
  { id: "near_station", label: "Near station" },
  { id: "shortest_travel", label: "Shortest travel" },
  { id: "quiet", label: "Quiet" },
  { id: "convenience_store", label: "Convenience store" },
  { id: "food_nightlife", label: "Food/nightlife" },
  { id: "best_value", label: "Best value" },
] as const;

type HotelBasePanelProps = {
  selectedChips: string[];
  notes: string;
  isRunning: boolean;
  placeCount: number;
  elapsedSeconds: number | null;
  progressItems: HotelBaseProgressItem[];
  onToggleChip: (chip: string) => void;
  onNotesChange: (value: string) => void;
  onContinue: () => void;
};

export type HotelBaseProgressItem = {
  id: string;
  title: string;
  detail: string;
  tone: "info" | "success";
};

export function HotelBasePanel({
  selectedChips,
  notes,
  isRunning,
  placeCount,
  elapsedSeconds,
  progressItems,
  onToggleChip,
  onNotesChange,
  onContinue,
}: HotelBasePanelProps) {
  return (
    <div>
      <p className="text-[10px] font-black uppercase tracking-[0.22em] text-teal-200">
        Hotel base
      </p>
      <h2 className="mt-1 text-xl font-black leading-6 tracking-tight text-white">
        Where should the trip orbit from?
      </h2>
      <p className="mt-1 line-clamp-2 text-xs font-semibold leading-5 text-slate-300">
        The agent will score base areas against {placeCount} mapped places before planning the route.
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {HOTEL_BASE_CHIPS.map((chip) => {
          const active = selectedChips.includes(chip.id);

          return (
            <button
              key={chip.id}
              type="button"
              disabled={isRunning}
              onClick={() => onToggleChip(chip.id)}
              className={[
                "rounded-full border px-2.5 py-1.5 text-[11px] font-black transition disabled:cursor-not-allowed disabled:opacity-60",
                active
                  ? "border-amber-200/60 bg-amber-200/18 text-amber-100"
                  : "border-white/10 bg-white/8 text-slate-200 hover:bg-white/12",
              ].join(" ")}
            >
              {chip.label}
            </button>
          );
        })}
      </div>

      <label className="mt-3 block">
        <span className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
          Hotel notes
        </span>
        <textarea
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
          disabled={isRunning}
          rows={2}
          placeholder="Optional: room style, loyalty, budget cap, avoid areas..."
          className="mt-1.5 min-h-[56px] w-full resize-none rounded-lg border border-white/10 bg-white/10 px-3 py-2 text-xs font-semibold leading-5 text-white outline-none transition placeholder:text-slate-500 focus:border-amber-200/60 disabled:cursor-not-allowed disabled:opacity-60"
        />
      </label>

      {progressItems.length > 0 || elapsedSeconds !== null ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">
              Progress
            </p>
            {elapsedSeconds !== null ? (
              <span className="rounded-full border border-white/10 bg-white/10 px-3 py-1 text-xs font-bold text-slate-200">
                {elapsedSeconds.toFixed(1)}s
              </span>
            ) : null}
          </div>
          {progressItems.slice(-4).map((item) => (
            <div
              key={item.id}
              className={[
                "rounded-lg border px-3 py-2",
                item.tone === "success"
                  ? "border-teal-200/25 bg-teal-300/10"
                  : "border-white/10 bg-white/8",
              ].join(" ")}
            >
              <p className="text-xs font-black text-white">{item.title}</p>
              <p className="mt-1 line-clamp-2 text-xs font-semibold leading-4 text-slate-300">
                {item.detail}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      <button
        type="button"
        disabled={isRunning}
        onClick={onContinue}
        className="mt-4 h-9 w-full rounded-lg border border-amber-100/30 bg-amber-200 px-4 text-[11px] font-black uppercase tracking-[0.14em] text-slate-950 shadow-xl shadow-amber-950/25 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isRunning ? "Optimizing base" : "Optimize hotel base"}
      </button>
    </div>
  );
}

export function buildHotelPreferencePayload(
  selectedChips: string[],
  freeText: string,
): HotelPreferencePayload {
  const chips = selectedChips.filter((chip) => chip !== "optimize_for_me");

  return {
    chips,
    free_text: freeText.trim(),
    optimize_for_me: chips.length === 0 && selectedChips.includes("optimize_for_me"),
  };
}
