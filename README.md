# TripCanvas

Team TripCanvas submission for the **Sea x OpenAI Regional Codex Hackathon - Singapore**.

Track: **(2) AI-Native Products & Operations**

TripCanvas is an AI-native travel planner that turns saved travel inspiration and personal requirements into a mapped, explainable, bookable trip plan. Instead of treating AI as a chat box beside a travel app, TripCanvas makes the AI workflow the operating layer: it extracts places from Instagram Reels, weighs them against dates, budget, origin, and preferences, researches tradeoffs, chooses a hotel base, sequences the itinerary, explains why each stop was chosen, and hands off to a human-approved AI-assisted AP2 + x402 hotel-payment flow.

## Demo Flow

1. Paste 3-4 Instagram Reel URLs, dates, budget, origin city, and trip preferences.
2. Backend agents extract real places from messy Reel content, geocode them, and weigh them against the traveler's constraints.
3. The frontend immediately moves from a Mapbox globe into the destination map.
4. Agents research places, weather, hotel-base tradeoffs, and itinerary feasibility.
5. TripCanvas renders the plan as a tilted Mapbox 3D map with pins, hotel base, day route segments, and itinerary cards.
6. Selecting any extracted place shows why the agent chose it, what to do there, evidence, timing, tradeoffs, and route context.
7. After approval, the hotel booking handoff uses AP2 mandate approval and an x402 payment loop.

For demo reliability, the UI also includes:

- **Demo Reels** quick fill for the canonical hackathon Reel set.
- **Backend Cache** one-click replay from committed backend caches.
- Clear source state when cache data is used.

## Why This Is AI-Native

TripCanvas is designed around AI-assisted operations, not AI autocomplete.

- **Messy input becomes structured action:** saved Reels, dates, budget, origin, and preferences are converted into real mapped places, hotel decisions, and a day-by-day itinerary.
- **The agent shows its work at product level:** users see confidence, evidence, source state, stage progress, hotel-base reasoning, weather strategy, and route tradeoffs without exposing hidden chain-of-thought.
- **The map is the planning surface:** the user does not read a static itinerary first; they inspect the agent's decisions spatially through a 3D map, selected-place rationale, and per-day route legs.
- **Operations are resilient:** live extraction/planning can fall back to committed cache data so the demo remains fast and dependable.
- **The final step is human-approved action:** payment is AI-assisted, but not AI-controlled. AP2 captures the user's explicit approval and constraints before the x402 payment loop runs.

## Human-in-the-Loop AI-Assisted Payment

Payment is a core part of TripCanvas, but the AI does not get unchecked control of money movement. The planning system moves from recommendation to constrained execution only after the user approves the hotel plan. The backend then creates an AP2-style mandate, verifies that mandate, and runs the x402 hotel-payment loop within the approved constraints.

What the demo shows:

- **AP2 approval:** the user authorizes a specific hotel-booking action before the agent can proceed.
- **Human in the loop:** the AI can prepare the flow, but the approval boundary stays with the user.
- **Mandate verification:** the backend checks the signed AP2 mandate before payment execution.
- **x402 payment loop:** after approval, the payment service performs the pay step through an x402-shaped request, proof, settlement, and receipt flow.
- **Frontend payment state:** the UI shows approval, x402 payment progress, receipt, transaction link, and wallet links when available.
- **AI-native operations:** TripCanvas demonstrates how an AI product can safely move from planning to action while keeping human approval and payment constraints explicit.

## Product Guardrails

TripCanvas is built to make AI useful without making it opaque or unchecked.

- **Human approval before payment:** AP2 records the user's approval and constraints before any x402 payment step can run.
- **Verified mandate:** `/hotel-booking` checks the signed AP2 mandate before executing the payment loop.
- **Constrained execution:** the payment handoff is scoped to the selected hotel booking, amount, and payment rail.
- **Evidence without hidden reasoning:** the UI shows confidence, source evidence, rationale, and tradeoffs, but not hidden chain-of-thought.
- **Reliable demo path:** committed caches and `GET /demo-cache` keep the live demo fast when scraping or long-running research is slow.
- **Typed contracts:** backend Pydantic models and frontend TypeScript contracts keep extracted places, itinerary data, payment state, and SSE payloads predictable.
- **Source visibility:** the UI labels cache/live source state so users know when the plan is replayed from the demo cache.

## Final Frontend State

The frontend is a Next.js App Router app in `frontend/`.

Implemented demo surface:

- Mapbox GL JS 3D globe as the first screen.
- Reel URL and preference input with dates, budget, origin city, and free-text travel requirements.
- `Demo Reels` and `Backend Cache` buttons for fast hackathon demos.
- Generation timeline for extract, map grounding, hotel base, itinerary planning, and approval.
- Full-screen tilted Mapbox 3D map with extracted-place pins.
- Left trip panel with detected places, confidence labels, day filters, and category filters.
- Extracted places are clickable; selecting one focuses the map and opens its explanation.
- Route rendering is broken into one-location-to-one-location legs, with the selected leg emphasized.
- Right AI panel explains the selected stop, evidence, tradeoffs, weather fit, and next action.
- Bottom itinerary rail shows day-by-day route cards.
- Human-in-the-loop payment panel for AP2 mandate approval and x402 hotel payment handoff.

Frontend stack:

- Next.js 15
- React 19
- Tailwind CSS v4
- `mapbox-gl` 3.24.0
- `NEXT_PUBLIC_MAPBOX_TOKEN`
- `NEXT_PUBLIC_BACKEND_URL`, defaulting to `http://localhost:8000`

## Final Backend State

The backend is a FastAPI service in `backend/`.

Core endpoints:

- `GET /health` - service health check.
- `GET /demo-cache` - instant replay of committed places, hotel-base, and itinerary caches.
- `POST /extract` - Reel URLs to extracted places, with cache fallback.
- `POST /hotel-base` - streams hotel-base optimization.
- `POST /itinerary` - POST SSE stream for final itinerary planning.
- `POST /ap2/hotel-booking-mandate` - creates a signed AP2-style hotel mandate.
- `POST /hotel-booking` - verifies mandate and runs the x402-shaped hotel payment loop.

Backend capabilities:

- OpenAI Agents SDK for extraction, research, hotel-base optimization, narration, and booking logic.
- Apify Instagram Reel scraper integration for Reel ingestion.
- Web research for place, hotel, flight, and itinerary context.
- Open-Meteo weather data.
- Committed demo caches:
  - `backend/data/places.json`
  - `backend/data/hotel_base_output.json`
  - `backend/data/planner_output.json`
- Organized implementation packages for API streaming, planner logic, and AP2 + x402 payments:
  - `backend/api/`
  - `backend/planner/`
  - `backend/payments/`
- Compatibility facades remain in `backend/spike_planner.py` and `backend/spike_agentic_payments.py`.

The backend keeps the demo dependable by separating live agent work from replayable cache data. The cache path is not a separate product mode; it is an operational guardrail for noisy network, scraper, and LLM latency during a live demo.

## Architecture

```text
Instagram Reels + traveler preferences
  -> Apify scraper
  -> OpenAI extraction agents
  -> real places + confidence + evidence
  -> Mapbox globe zooms into destination
  -> hotel-base agent chooses base area and hotel candidate
  -> planner agents research weather, routing, timing, and preferences
  -> itinerary JSON + payment context
  -> Mapbox 3D trip canvas
  -> AP2 approval
  -> x402 hotel payment handoff
```

Frontend consumes `/itinerary` with `fetch()` streaming because it is a POST SSE endpoint. Streams terminate with:

```text
data: {"type":"result","content":"<final JSON string>"}
data: [DONE]
```

## Running Locally

Backend:

```bash
uv sync
uv run uvicorn backend.main:app --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

Required environment:

```bash
OPENAI_API_KEY=...
APIFY_TOKEN=...
NEXT_PUBLIC_MAPBOX_TOKEN=...
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

## Demo Script

1. Start backend on `8000` and frontend on `3000`.
2. Open TripCanvas.
3. Click **Demo Reels** or paste the test Reel URLs.
4. For the fastest path, click **Backend Cache**.
5. Show the map zoom, extracted places, hotel base, selected route leg, and right-side AI explanation.
6. Click a non-selected extracted place to show that the map and rationale update.
7. Approve the AP2 hotel mandate.
8. Run the x402 hotel payment handoff.

## Judging Alignment

**AI-native product:** The product flow starts from unstructured social media, not a form full of known destinations. AI shapes the core UX, data model, decision flow, and operation loop.

**Operational depth:** TripCanvas models the work a human travel planner would do: identify real places, check feasibility, choose a hotel base, sequence days, reason about rain and transit, and prepare payment.

**Human-in-the-loop AI-assisted payment:** The project goes beyond itinerary generation by showing AP2 approval before x402 payment execution, making the agent useful for a constrained operational step without giving it unchecked payment control.

**Transparency and trust:** The UI shows user-facing rationale, evidence, confidence, cache/live source state, and tradeoffs so the user can approve or redirect the agent.

**Demo reliability:** The backend has committed cache artifacts and a `/demo-cache` endpoint so the hackathon demo remains fast even when live scraping or long-running agent research is slow.

**Technical integration:** The system combines OpenAI Agents SDK, FastAPI SSE, Apify, Mapbox GL JS, Open-Meteo, AP2-style human approval mandates, and x402-shaped payment settlement behind typed frontend contracts.

## Verification

Frontend checks, from `frontend/`:

```bash
cd frontend
npm run test:unit
npm run typecheck
npm run build
```

Backend checks, from the repo root:

```bash
uv run pytest backend/tests -q
```

The latest implementation was verified with backend pytest, frontend unit tests, TypeScript, production build, and browser checks against the backend cache flow.
