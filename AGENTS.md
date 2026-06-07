# Agent Instructions

This project is TripCanvas.

## Current Product Direction

TripCanvas is an AI-native travel planner. The main demo flow stays aligned with
`CLAUDE.md`:

1. User provides 3-4 Instagram Reel URLs, travel dates, and free-text
   preferences.
2. Backend agents extract real places, research them live, recommend 3 hotels
   (with one best pick), assemble a day-by-day itinerary, and run an agentic
   payment (AP2 + x402) over mock bookings.
3. Frontend renders the trip on a **Mapbox 3D map** from backend or sample data.
4. Selecting a place, especially a hotel, should expose a streaming AI agent
   recommendation panel.

**Pivot (2026-06-06) — `CLAUDE.md` is now fully aligned with these and is the
source of truth. Current repo status was refreshed on 2026-06-07:**

- **Surface:** a **Mapbox 3D / tilted map** is the primary UI/UX, NOT a pop-up
  book / flipbook / `react-pageflip` / Google Maps. These are permanently
  dropped — do not reintroduce them.
- **Payments:** Duffel is deprecated. The agent performs a **real agentic
  payment** via **AP2** (signed Intent/Cart mandates) **+ x402** (HTTP-402 →
  `X-PAYMENT` → facilitator settles USDC). The explicit hotel-payment endpoint
  implementation lives in `backend/payments/`, with compatibility exports from
  `backend/spike_agentic_payments.py`; the itinerary booking overlay still has
  the older `PaymentProvider` seam in `spike_booking.py`. The
  **booking/fulfillment stays mock** (`is_mock=True`); the payment is the
  headline. **Ownership:** Zhi Hao owns real AP2/x402 provider work; local demo
  defaults remain simulation/mock-safe.
- **Hotels:** the itinerary shows **3 hotel recommendations + 1 best pick**
  (`ItineraryOutput.hotel_options`, one with `is_best=true`; `recommended_hotel`
  is the best pick).
- **Current baseline:** the repo now includes the Mapbox generation shell,
  extracted-place map feedback, itinerary panels, and AP2/x402 hotel-payment UI.
  Future frontend work should be incremental and should not replace the main
  Mapbox-first flow unless the user explicitly changes direction.

Keep `CLAUDE.md` as the source of truth for the backend pipeline, data flow, SSE
contract, cache fallback, demo guardrails, payment services, and agent orchestration.

## Hackathon Positioning

The differentiator is not "a nice map." The differentiator is the AI-native
agent experience:

- Show the agent turning messy saved Reels into real, mapped travel decisions.
- Make live/cache source state, extraction confidence, evidence, and research
  progress visible when useful.
- Keep the streaming agent panel central to the demo loop.
- Show travel-domain judgment: hotel tradeoffs, route feasibility, neighborhood
  fit, timing, preferences, and itinerary sequencing.
- Show autonomous and adaptive behavior through stage progress, fallbacks, and
  resilient handling of incomplete or noisy inputs.
- Do not expose hidden chain-of-thought. Show user-facing rationale, evidence,
  tool/status updates, and final recommendations.

## Before Frontend Changes

Read these before making frontend changes:

- `CLAUDE.md` for backend contracts and the main demo flow.
- `README.md` for the implemented demo surface and verification commands.
- `frontend/package.json` for the actual installed frontend stack.
- `frontend/app/` structure.
- `frontend/components/` and `frontend/lib/` structure.

If docs conflict, prefer this order for frontend decisions:

1. This `AGENTS.md`
2. `CLAUDE.md` backend/data contracts
3. `README.md`
4. Existing frontend code

## Frontend Architecture

Use the existing Next.js App Router frontend in `frontend/`.

- Use `mapbox-gl` for the main map surface.
- The first screen is a Mapbox globe generation surface, not a static landing
  page.
- User input starts the backend agent pipeline from Instagram Reels.
- The globe must zoom into the extracted destination as soon as `/extract`
  returns valid places. Do not wait for the full itinerary before showing map
  feedback.
- Consume `/itinerary` with `fetch()` streaming because it is a POST SSE
  endpoint; native `EventSource` is not suitable for this endpoint.
- Keep map rendering client-side only.
- Use React DOM overlays for panels, cards, rails, and controls.
- Use `NEXT_PUBLIC_MAPBOX_TOKEN` for the public Mapbox token. Do not commit
  tokens or secrets.
- Use `NEXT_PUBLIC_BACKEND_URL` for the frontend-to-FastAPI base URL, defaulting
  to `http://localhost:8000` in local demo code.
- Do not add Google Maps, MapLibre, Three.js, Framer Motion, or another
  map/rendering/animation engine for the generation flow unless the user
  explicitly changes direction.
- Do not rebuild the app around a flipbook, page-turn interaction, or pop-up
  book metaphor.
- Keep hardcoded Tokyo demo data only as fallback, not the primary entry flow.

Expected Mapbox workspace:

- Opening globe with Reel URL, date, budget, origin, and preference inputs.
- Generation timeline for extraction, map zoom, itinerary planning, and final
  render.
- Full-screen tilted/3D map background.
- Left trip panel for destination, dates, preferences, detected places, and day
  selection.
- Map pins, selected-place camera movement, route lines, and category/day
  filtering.
- Right panel for streaming AI agent output and hotel/place recommendations.
- Bottom rail for saved places or itinerary cards.
- Source and fallback state should be visible when the backend returns cache
  data.

## Implementation Priorities

- Prefer small, reviewable changes.
- Do not rewrite the whole app unless explicitly asked.
- Match existing styling and component conventions.
- Use typed data contracts for backend responses.
- Preserve the SSE termination contract from `CLAUDE.md`.
- Add loading, empty, and error states for user-facing async flows.
- Keep demo reliability ahead of visual polish.
- Prefer committed sample/cache data when needed to keep the demo loop working.
- Do not put secrets or private API keys in frontend code.

## Ask Before Large Changes

Ask before:

- Changing the main Reel URLs -> extraction -> itinerary -> map -> agent panel
  flow.
- Removing or de-emphasizing the AI agent panel.
- Changing backend response schemas or SSE event contracts.
- Swapping Mapbox for another map provider.
- Adding heavy new visualization, animation, or orchestration libraries.
- Making broad architectural rewrites that are not required for the requested
  task.
