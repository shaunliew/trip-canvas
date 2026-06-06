# AI-Native Mapbox Frontend Design

## Context

TripCanvas is an AI-native travel planner for the OpenAI SEA hackathon. The backend flow is owned separately and already exposes the important contract: users submit Instagram Reel URLs and trip preferences, `/extract` returns grounded places, `/hotel-base` can stream base-area decisions, and `/itinerary` streams the final day-by-day plan.

The frontend already has the right bones: Next.js App Router, Mapbox GL JS, a globe-to-map generation shell, streaming panels, place intel, hotel-base UI, route layers, selected-place camera movement, and fallback source badges. The redesign should therefore be a focused presentation and interaction pass, not a rewrite.

## Mapbox Notes

Mapbox GL JS supports the interaction model TripCanvas needs:

- Use `mapbox://styles/mapbox/standard` with `config.basemap` for a configurable Standard style.
- Use `projection: "globe"` for the opening globe and switch to mercator for the tilted trip map.
- Use `setFog` for atmosphere, `flyTo` for selected places, and `fitBounds` for extracted destination focus.
- Use GeoJSON sources and line/circle/symbol layers for route lines, pins, hub markers, and selected/dimmed states.
- Use Mapbox layer events for click/hover interactions; the current implementation already follows this pattern.

Primary documentation references used:

- https://docs.mapbox.com/mapbox-gl-js/guides/styles/set-a-style/
- https://docs.mapbox.com/mapbox-gl-js/example/initial-config-property/
- https://docs.mapbox.com/mapbox-gl-js/example/center-on-feature/
- https://docs.mapbox.com/mapbox-gl-js/example/geojson-line/
- https://docs.mapbox.com/mapbox-gl-js/example/zoomto-linestring/

## Design Thesis

The frontend should feel like an AI travel cockpit over a real 3D map. The impressive part is not visual complexity; it is seeing the agent convert messy Reel inputs into grounded travel decisions with source state, confidence, tradeoffs, hotel-base logic, and route sequencing.

## User Flow

1. First screen is the Mapbox globe generation surface with the input panel already available.
2. User enters 1-4 Reel URLs, dates, budget, origin, and free-text preferences.
3. `/extract` runs and the map immediately focuses extracted places before itinerary planning.
4. The interface shows a compact stage model: extract, ground, base, plan, approve.
5. Hotel-base optimization remains a visible AI decision step.
6. `/itinerary` streams planner progress into a right-side agent panel.
7. Final workspace emphasizes the selected day, selected place, selected hotel hub, and active route.
8. Clicking a map pin or bottom rail item highlights that place, dims other visible stops, moves the camera, and explains why the agent chose it.
9. User can approve the plan; booking/payment remains a clear placeholder handoff for teammates.

## Visual System

- Keep the map full-screen and dominant.
- Reduce panel copy density and oversized headings.
- Use one active explanation at a time: decision, evidence, tradeoff, next action.
- Use small status chips for source/cache/confidence instead of long blocks.
- Keep dimmed non-selected map places visible, so users understand context while focusing.
- Keep the right panel central to the demo loop on desktop and available as a bottom panel on smaller screens.

## In Scope

- Frontend-only changes under `frontend/`.
- Documentation plan under `docs/superpowers/`.
- Map dimming and selected-day route emphasis.
- First-screen input over the Mapbox globe, with no click-through landing gate.
- Cleaner generation timeline and agent panel copy.
- Stronger place intel focused on why chosen, what to do there, evidence, and travel fit.
- Final plan approval and booking placeholder.
- Pure helper tests where logic is extracted.

## Out Of Scope

- Backend endpoint/schema changes.
- Real payment or booking checkout.
- New visualization libraries.
- Map provider changes.
- Replacing Mapbox with custom 3D scenes.
- Rebuilding the application shell from scratch.

## Acceptance Criteria

- `NEXT_PUBLIC_MAPBOX_TOKEN` remains the only required public map token.
- First load shows a Mapbox globe with the Reel input form available immediately.
- Extracted places still zoom the map before itinerary streaming begins.
- Selected places are visually dominant on the map while other visible places are dimmed.
- Selected place rationale is visible without requiring the user to parse raw logs.
- Hotel-base and final itinerary streaming panels still work with POST SSE via `fetch()`.
- Final trip has an approve/booking placeholder that does not claim real payment.
- `npm run typecheck` and `npm run build` succeed in `frontend/`.
