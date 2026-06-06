import type {
  CategoryFilter,
  DayFilter,
  PlaceCategory,
  TripHotelBase,
  TripExperience,
} from "@/lib/trip/types";

type LeftTripPanelProps = {
  trip: TripExperience;
  selectedDay: DayFilter;
  activeCategory: CategoryFilter;
  categories: PlaceCategory[];
  visiblePlaceCount: number;
  hotelBase?: TripHotelBase;
  onSelectDay: (day: DayFilter) => void;
  onSelectCategory: (category: CategoryFilter) => void;
};

export function LeftTripPanel({
  trip,
  selectedDay,
  activeCategory,
  categories,
  visiblePlaceCount,
  hotelBase,
  onSelectDay,
  onSelectCategory,
}: LeftTripPanelProps) {
  const activeDay =
    selectedDay === "all"
      ? null
      : (trip.days.find((day) => day.day === selectedDay) ?? null);

  return (
    <aside className="absolute left-3 top-3 z-10 max-h-[42vh] w-[calc(100vw-1.5rem)] max-w-[350px] overflow-y-auto rounded-xl border border-amber-100/15 bg-[#111923]/78 p-3 shadow-2xl shadow-black/30 backdrop-blur-xl md:left-4 md:top-4 lg:max-h-[calc(100vh-8rem)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[9px] font-black uppercase tracking-[0.24em] text-amber-200">
            TripCanvas
          </p>
          <h1 className="mt-1 line-clamp-2 text-lg font-black leading-5 tracking-tight text-white md:text-xl">
            {trip.title}
          </h1>
          <p className="mt-1 truncate text-xs font-semibold text-slate-300">
            {trip.destination.city}, {trip.destination.country} -{" "}
            {trip.datesLabel}
          </p>
        </div>
        <span className="shrink-0 rounded-full border border-teal-200/30 bg-teal-300/15 px-2.5 py-1 text-[10px] font-bold text-teal-100">
          Live map
        </span>
      </div>

      {hotelBase ? (
        <section className="mt-3 rounded-lg border border-cyan-100/15 bg-cyan-300/8 p-2.5">
          <p className="text-[9px] font-black uppercase tracking-[0.2em] text-teal-200">
            Hotel base
          </p>
          <p className="mt-1 truncate text-sm font-black text-white">
            {hotelBase.selectedBaseName}
          </p>
          <p className="mt-1 line-clamp-2 text-[11px] font-semibold leading-4 text-slate-300">
            {hotelBase.selectedBaseRationale}
          </p>
        </section>
      ) : null}

      <section className="mt-3">
        <p className="mb-2 text-[9px] font-black uppercase tracking-[0.22em] text-slate-400">
          Days
        </p>
        <div className="flex flex-wrap gap-1.5">
          <FilterButton
            active={selectedDay === "all"}
            onClick={() => onSelectDay("all")}
          >
            All
          </FilterButton>
          {trip.days.map((day) => (
            <FilterButton
              key={day.day}
              active={selectedDay === day.day}
              onClick={() => onSelectDay(day.day)}
            >
              Day {day.day}
            </FilterButton>
          ))}
        </div>
        {activeDay ? (
          <div className="mt-2 rounded-lg border border-white/10 bg-white/8 p-2.5">
            <p className="text-[9px] font-black uppercase tracking-[0.18em] text-amber-200">
              {activeDay.title}
            </p>
            <p className="mt-1 line-clamp-2 text-[11px] font-semibold leading-4 text-slate-300">
              {activeDay.summary}
            </p>
            {activeDay.stops && activeDay.stops.length > 0 ? (
              <ol className="mt-2 space-y-1.5">
                {activeDay.stops.map((stop, index) => (
                  <li key={`${stop.timeOfDay}-${index}`} className="flex gap-2">
                    <span className="mt-0.5 w-[3.25rem] shrink-0 text-[8px] font-black uppercase tracking-[0.12em] text-teal-200">
                      {stop.timeOfDay}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-[11px] font-bold text-white">
                        {stop.name}
                        {stop.isAnchor ? (
                          <span className="ml-1 rounded bg-amber-200/20 px-1 py-0.5 text-[8px] font-black uppercase tracking-wide text-amber-200">
                            {stop.category === "hotel" ? "stay" : "main"}
                          </span>
                        ) : null}
                      </p>
                      {stop.description ? (
                        <p className="mt-0.5 line-clamp-2 text-[10px] font-medium leading-snug text-slate-400">
                          {stop.description}
                        </p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            ) : null}
            {activeDay.weatherStrategy ? (
              <div className="mt-2 rounded-lg border border-sky-200/15 bg-sky-200/8 p-2 xl:hidden">
                <p className="text-[9px] font-black uppercase tracking-[0.18em] text-sky-200">
                  Weather strategy
                </p>
                <p className="mt-1 line-clamp-2 text-[11px] font-semibold leading-4 text-slate-200">
                  {activeDay.weatherStrategy}
                </p>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="mt-3">
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-[9px] font-black uppercase tracking-[0.22em] text-slate-400">
            Categories
          </p>
          <span className="text-[11px] font-semibold text-slate-400">
            {visiblePlaceCount} visible
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <FilterButton
            active={activeCategory === "all"}
            onClick={() => onSelectCategory("all")}
          >
            All
          </FilterButton>
          {categories.map((category) => (
            <FilterButton
              key={category}
              active={activeCategory === category}
              onClick={() => onSelectCategory(category)}
            >
              {category}
            </FilterButton>
          ))}
        </div>
      </section>
    </aside>
  );
}

function FilterButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded-full border px-2.5 py-1 text-[11px] font-bold capitalize shadow-lg transition",
        active
          ? "border-amber-200 bg-amber-200/18 text-white"
          : "border-white/10 bg-white/10 text-slate-200 hover:bg-white/16",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
