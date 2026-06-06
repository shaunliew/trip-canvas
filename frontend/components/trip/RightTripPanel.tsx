import { PlaceIntelPanel } from "@/components/trip/PlaceIntelPanel";
import type { TripDay, TripPlace } from "@/lib/trip/types";

export type RightPanelTab = "agent-run" | "place-intel";

type RightTripPanelProps = {
  activeTab: RightPanelTab;
  agentPanelContent?: React.ReactNode;
  days: TripDay[];
  places: TripPlace[];
  selectedPlace: TripPlace | null;
  routePreviewPlaceId?: string | null;
  mobileIntelOpen?: boolean;
  lockedPlaceIds?: Set<string>;
  onTogglePlaceLock?: (placeId: string) => void;
  onPreviewRoute?: (placeId: string) => void;
  onRequestRegenerateDay?: (day: number) => void;
  onCloseMobileIntel?: () => void;
  onSelectTab: (tab: RightPanelTab) => void;
};

export function RightTripPanel({
  activeTab,
  agentPanelContent,
  days,
  places,
  selectedPlace,
  routePreviewPlaceId,
  mobileIntelOpen = false,
  lockedPlaceIds,
  onTogglePlaceLock,
  onPreviewRoute,
  onRequestRegenerateDay,
  onCloseMobileIntel,
  onSelectTab,
}: RightTripPanelProps) {
  return (
    <>
      <aside className="absolute right-3 top-3 z-10 hidden max-h-[calc(100vh-7.25rem)] w-[350px] flex-col overflow-hidden rounded-xl border border-amber-100/15 bg-[#101821]/86 shadow-2xl shadow-black/35 backdrop-blur-xl lg:flex xl:right-4 xl:top-4 xl:w-[380px]">
        <div className="grid grid-cols-2 gap-1.5 border-b border-white/10 p-2">
          <TabButton
            active={activeTab === "agent-run"}
            disabled={!agentPanelContent}
            onClick={() => onSelectTab("agent-run")}
          >
            Agent
          </TabButton>
          <TabButton active={activeTab === "place-intel"} onClick={() => onSelectTab("place-intel")}>
            Why this
          </TabButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {activeTab === "agent-run" && agentPanelContent ? (
            agentPanelContent
          ) : (
            <PlaceIntelPanel
              place={selectedPlace}
              days={days}
              places={places}
              routePreviewActive={selectedPlace ? routePreviewPlaceId === selectedPlace.id : false}
              locked={selectedPlace ? lockedPlaceIds?.has(selectedPlace.id) ?? false : false}
              onToggleLock={onTogglePlaceLock}
              onPreviewRoute={onPreviewRoute}
              onRequestRegenerateDay={onRequestRegenerateDay}
            />
          )}
        </div>
      </aside>

      {mobileIntelOpen && selectedPlace ? (
        <aside className="absolute bottom-3 left-3 right-3 z-30 max-h-[76dvh] overflow-hidden rounded-xl border border-amber-100/15 bg-[#101821]/94 shadow-2xl shadow-black/45 backdrop-blur-xl lg:hidden">
          <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-amber-100">
              Why this stop
            </p>
            <button
              type="button"
              onClick={onCloseMobileIntel}
              className="h-8 rounded-lg border border-white/10 bg-white/8 px-3 text-[11px] font-black uppercase tracking-[0.12em] text-slate-200"
            >
              Close
            </button>
          </div>
          <div className="max-h-[calc(76dvh-45px)] overflow-y-auto p-3">
            <PlaceIntelPanel
              place={selectedPlace}
              days={days}
              places={places}
              routePreviewActive={routePreviewPlaceId === selectedPlace.id}
              locked={lockedPlaceIds?.has(selectedPlace.id) ?? false}
              onToggleLock={onTogglePlaceLock}
              onPreviewRoute={onPreviewRoute}
              onRequestRegenerateDay={onRequestRegenerateDay}
            />
          </div>
        </aside>
      ) : null}
    </>
  );
}

function TabButton({
  active,
  disabled,
  children,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        "h-8 rounded-lg border text-[11px] font-black uppercase tracking-[0.13em] transition disabled:cursor-not-allowed disabled:opacity-40",
        active
          ? "border-amber-200/50 bg-amber-200/16 text-amber-100"
          : "border-white/10 bg-white/8 text-slate-300 hover:bg-white/12",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
