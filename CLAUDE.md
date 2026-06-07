# TripCanvas — Claude Code Project Instructions

## What we are building

AI-native travel planner. User pastes 3-4 Instagram Reel URLs + travel dates + budget + origin city + free-text preferences. Backend extracts real places, researches them live, fetches weather, recommends 3 hotels (with one best pick), assembles a day-by-day itinerary, and runs an **agentic payment** (AP2 + x402) over **mock** bookings. Frontend renders a **Mapbox 3D map** (tilted/3D globe → zoom-in city map) → streaming AI agent panel.

> **Pivot note (2026-06-06):** (1) Frontend is a **Mapbox 3D map**, NOT a flipbook/pop-up book. (2) Payments moved from Duffel to an **AP2 + x402 agentic-payment seam** — the *payment* is the headline ("the agent really pays"), the *booking/fulfillment stays mock* (`is_mock=True`). (3) Itinerary hotels are now **3 recommendations + 1 best pick**. Current code round is **backend-only**; the 3D-map frontend revamp is a separate next round.

Hackathon: Sea × OpenAI Codex Hackathon, 6 June 2026, Singapore.
Code freeze: 17:00 SGT. One tight demo loop beats three half-built features.

---

## Team Roles

| Person | Owns |
|--------|------|
| Shaun  | **Frontend 3D Mapbox revamp** + **backend agent logic**: extract (`spike_e2e.py`), planner/narrator (`spike_planner.py`), weather (`spike_weather.py`), hotel-base 3-rec (`spike_hotel_base.py`), FastAPI SSE (`main.py`), demo reliability |
| Zhi Hao | **Agentic payment**: AP2 (Intent/Cart mandates) + x402 (HTTP-402 settlement) wired into the `PaymentProvider` seam in `spike_booking.py` (replaces the default `MockSettlementProvider` with a real AP2-mandate → x402-facilitator client) |
| Cody  | Pydantic schemas + agent code (weather / booking / hotel-base), collab w/ Shaun on planner integration |

> Round split: **this round = backend + docs (Shaun's agent logic + hotel 3-rec + the payment seam stub)**. **Next round = frontend 3D-map revamp (Shaun)** and **real AP2/x402 settlement (Zhi Hao)**.

---

## Exact Stack — do not substitute

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router) + React 19 + Tailwind v4 + **mapbox-gl 3.24.0** |
| Map | **Mapbox GL JS only**, **3D/tilted** (NOT Google Maps, NOT MapLibre, NOT Three.js, NOT a flipbook) |
| Backend | FastAPI (Python ≥3.14) + Server-Sent Events |
| Reel ingestion | **Apify MCP** via `MCPServerStreamableHttp` → `https://mcp.apify.com/?tools=actors,docs,apify/instagram-reel-scraper` |
| LLM reasoning | OpenAI Agents SDK `Agent(model="gpt-5.5-2026-04-23")` + `gpt-4o` typed fallback + `WebSearchTool` |
| Place extraction | `_extract_for_reel` agent in `spike_e2e.py`: `output_type=ExtractionResult`, `WebSearchTool` for geocoding |
| Hotel recommendation | `hotel_base_agent` in `spike_hotel_base.py`: **3 hotel candidates + 1 best pick** (`selected_hotel_id`), all in the selected base area |
| Itinerary planning | `enricher` + `narrator_agent` in `spike_planner.py` (carries `hotel_options` = the 3 recs) |
| Weather | **Open-Meteo** HTTP (free, no API key, 10k calls/day) wrapped as `function_tool` |
| **Agentic payment** | **AP2** (Agent Payments Protocol — signed Intent/Cart mandates = authorization) **+ x402** (Coinbase HTTP-402 → `X-PAYMENT` header → facilitator settles USDC = settlement). Modeled as a `PaymentProvider` seam; default `MockSettlementProvider` this round, real client owned by Zhi Hao |
| Booking — flights | **Skyscanner deep-link composer** + `TC-MOCK-{sha1[:8]}` id (mock fulfillment). *Duffel sandbox = deprecated optional fallback, only if `DUFFEL_TEST_TOKEN` set* |
| Booking — hotels | **Booking.com search-URL composer** (no auth) + `TC-MOCK-{sha1[:8]}` id |
| Booking — attractions | **Klook search-URL composer** (no auth) + `TC-MOCK-{sha1[:8]}` id |
| Booking overlay | Pydantic `BookingResult` with `is_mock=True` on every item; each item carries an optional `settlement` (AP2/x402 `PaymentSettlement`) |
| Multi-agent | OpenAI Agents SDK (`uv add openai-agents openai`) — `from agents import Agent, Runner` |
| Package manager | `uv` (`pyproject.toml` at PROJECT ROOT, not `backend/`) |

Dropped / never-used (don't reintroduce): react-pageflip, flipbook/pop-up book, Framer Motion, Google Maps, MapLibre, Three.js, ffmpeg, transcription, Google Places, yt-dlp, requirements.txt.

**Payment vs booking — the core demo distinction:** the *payment* (AP2 mandate + x402 settlement) is the real, agent-driven act we showcase; the *booking/fulfillment* is always mock (`is_mock=True`). These are **separate fields**: `BookingItem.status` (`reserved`/`confirmed`) is fulfillment; `BookingItem.settlement` (`payment_status`, `settlement_id`, `payment_protocol`, `is_mock_settlement`) is payment. Never conflate them.

---

## SSE Stream Termination Contract (MUST match frontend)

Every SSE stream ends with both, in this order:
1. `data: {"type": "result", "content": "<final JSON string>"}\n\n`
2. `data: [DONE]\n\n`

Frontend `parseSseStream` (`frontend/lib/trip/sse.ts`) breaks on `data: [DONE]`. The JSON `{type:"done"}` event is NOT used. Error paths also terminate with `[DONE]`.

Optional stage events for demo visibility:
`data: {"type":"stage","stage":"weather"|"booking"|"narrator","msg":"..."}\n\n`
Frontend tolerates unknown event types — adding stage events is non-breaking.

---

## Env Vars (required at startup)

Backend (required):
```
OPENAI_API_KEY
APIFY_TOKEN
```

Backend (optional — every one of these is optional; `USE_CACHE=true` needs NONE of them):
```
USE_CACHE             # "true" to bypass live extraction, use data/places.json
DEMO_REEL_URLS        # comma-separated reel URLs for spike scripts (e.g. url1,url2,url3,url4)
DEMO_REEL_URL         # single-URL fallback — DEMO_REEL_URLS takes precedence
BOOKING_AID           # optional Booking.com affiliate id, may be empty for hackathon

# --- Agentic payment (AP2 + x402) — Zhi Hao's domain ---
USE_MOCK_PAYMENT      # "true" (default) → MockSettlementProvider, no network. "false" → real provider (next round)
X402_FACILITATOR_URL  # x402 facilitator endpoint for verify+settle (e.g. Coinbase CDP). Unused while mock
PAYMENT_NETWORK       # settlement chain e.g. "base-sepolia" (testnet) | "base". "mock" when USE_MOCK_PAYMENT
AP2_MANDATE_SIGNING_KEY  # key/keyref for signing AP2 Intent/Cart mandates. Placeholder until real client lands
X402_PAYER_ADDRESS    # agent wallet address used by x402 (testnet USDC). Placeholder until real client lands

# --- Deprecated (optional fallback only) ---
DUFFEL_TEST_TOKEN     # DEPRECATED. If set, MUST contain "_test_" (guard still enforced). Absent → Duffel path skipped, no startup abort
```

Frontend:
```
NEXT_PUBLIC_MAPBOX_TOKEN
NEXT_PUBLIC_BACKEND_URL    # defaults to http://localhost:8000
```

---

## Project File Structure (ground truth — organized compatibility layout)

```
tripcanvas/
├── pyproject.toml                  # PROJECT ROOT (not backend/)
├── backend/
│   ├── __init__.py                 # package marker; backend imports are package-qualified
│   ├── main.py                     # FastAPI app construction, CORS, route declarations, service calls
│   ├── api/
│   │   ├── schemas.py              # FastAPI request/response models
│   │   └── streaming.py            # SSE helpers, cache fallback, itinerary/hotel-base streams
│   ├── planner/
│   │   ├── models.py               # planner Pydantic/data models
│   │   ├── hotel_options.py        # hotel-option shaping helpers
│   │   ├── prompts.py              # planner prompt builders
│   │   └── runner.py               # enricher, narrator_agent, validation, planner runtime
│   ├── payments/
│   │   ├── models.py               # AP2/x402 Pydantic models and exceptions
│   │   ├── hotel_tool.py           # hotel payment tool loading
│   │   ├── ap2.py                  # AP2 mandate signing/verification helpers
│   │   ├── x402.py                 # x402 adapters
│   │   └── service.py              # AgenticHotelPaymentService orchestration
│   ├── spike_planner.py            # compatibility facade re-exporting planner.runner names
│   ├── spike_agentic_payments.py   # compatibility facade re-exporting payments service/private helpers
│   ├── spike.py                    # Phase 0 MCP smoke (not in serving path)
│   ├── spike_places.py             # Phase 0.5 smoke (not in serving path)
│   ├── spike_e2e.py                # ReelData, ExtractionResult, _scrape_reel, _extract_for_reel
│   ├── spike_e2e_planner.py        # run_extraction + run_pipeline orchestrator
│   ├── spike_weather.py            # weather_agent + fetch_weather (Open-Meteo)
│   ├── spike_hotel_base.py         # hotel_base_agent: 3 hotel candidates + best pick (selected_hotel_id)
│   ├── spike_booking.py            # booking_agent + deep-link composers + PaymentProvider seam (AP2/x402; Duffel deprecated)
│   └── data/                       # one JSON per purpose — no duplicate result files
│       ├── places.json             # COMMITTED cache (extract fallback)
│       ├── hotel_base_output.json  # COMMITTED cache (3 hotel candidates + best pick)
│       └── planner_output.json     # COMMITTED — THE single canonical itinerary result (hotel_options + settlements)
└── frontend/
    ├── app/page.tsx                # routes to TripGenerationShell
    ├── app/trip/page.tsx           # same shell
    ├── components/map/TripMap.tsx
    ├── components/trip/{TripGenerationShell,ReelInputPanel,GenerationTimeline,AgentDecisionRail,BookingFlowPanel}.tsx
    ├── components/trip/{TripCanvasShell,RightTripPanel,PlaceIntelPanel,SelectedPlaceCard}.tsx
    ├── lib/trip/{backend-types,generate-trip,normalize-trip,sse,types,place-intel}.ts
    ├── lib/trip/{generation-state,booking-flow,map-feature-collections,map-layers,map-runtime}.ts
    └── package.json                # mapbox-gl 3.24.0
```

Legacy imports through `backend.spike_planner` and `backend.spike_agentic_payments` remain supported while the implementation lives in `backend/planner/` and `backend/payments/`. Keep public endpoint contracts, response schemas, and the SSE `result` then `[DONE]` termination contract stable when working across these facades.

Earlier docs described `backend/lib/agents/{triage,research,hotels,transport,narrator}.py` and `backend/lib/extract/{apify_mcp,place_extractor,pipeline}.py`. THOSE FILES DO NOT EXIST. Use the organized package layout above, and do not reintroduce the old `backend/lib` placeholder.

---

## Architecture Data Flow

```
[Reel URLs × N]
  → Stage 1: sequential Apify scrapes inside one MCP context (~22s/reel measured)
       _scrape_reel agent → ReelData {caption, locationName, shortCode}

  → Stage 2: asyncio.gather — N place extractions in PARALLEL
       _extract_for_reel agent (gpt-5.5-2026-04-23, gpt-4o fallback)
           ModelSettings(tool_choice="required", parallel_tool_calls=True)
           tools=[WebSearchTool(search_context_size="high")]
           output_type=ExtractionResult

  → _flatten_and_dedup_by_name + _top_n_by_confidence (cap _MAX_PLACES=5)
  → /extract returns ExtractResponse {places, source, count} ← frontend zooms 3D map

  → /hotel-base SSE (optional, pre-itinerary):
        hotel_base_agent → 3 hotel_candidates (all in selected_base) + selected_hotel_id (best pick)

  → /itinerary SSE:
        asyncio.gather(
            enricher,                  # research + hotel + flight (WebSearchTool, batched)
            weather_agent,             # Open-Meteo function tool, parallel
        ) → EnrichedContext (incl. weather_report)
        → asyncio.gather(
            narrator_agent,            # assembles ItineraryOutput JSON
            booking_agent,             # deep-link composers + PaymentProvider.settle() per item (AP2/x402 mock)
          )
        → ItineraryOutput (incl. hotel_options[3, one is_best], bookings[items w/ settlement])
  → SSE: start → heartbeat ×N → stage ×K (optional) → result → [DONE]
```

Empirical timings (measured 2026-05-27):

| Stage | Measured | Notes |
|---|---:|---|
| Apify per-reel scrape | ~22s | Agent-loop overhead — multiply actor budget by ~1.5 |
| 4-reel extraction total | 215s live | Reliably blows the 80s timeout |
| Enricher (5 places, 8 searches) | 144.7s | At top of 90-130s budget |
| Narrator (4-day JSON) | 27.3s | On target |
| Full **cache-path** pipeline | **172s** | Demo runs via cache |

Cache path is THE demo path. Live extraction blows `_EXTRACTION_TIMEOUT=80s` in normal network conditions; backend auto-falls back to `data/places.json` and sets `"source": "cache"`.

---

## Apify MCP Wiring (verified)

```python
async with MCPServerStreamableHttp(
    name="Apify MCP Server",
    params={
        "url": "https://mcp.apify.com/?tools=actors,docs,apify/instagram-reel-scraper",
        "headers": {"Authorization": f"Bearer {os.environ['APIFY_TOKEN']}"},
        "timeout": 120,
    },
    cache_tools_list=True,
    max_retry_attempts=3,
    client_session_timeout_seconds=300,   # CRITICAL: default 5s always times out
) as server:
    agent = Agent(name="reel_scraper", model="gpt-5.5-2026-04-23",
                  mcp_servers=[server], max_turns=4, ...)
```

- Actor slug: `apify/instagram-reel-scraper`. Fields returned: `videoUrl`, `caption`, `audioUrl`, `locationName`, `locationId`, `shortCode`.
- Two-step flow: actor tool returns run metadata → call `get-dataset-items` with `datasetId` for content.
- `audioUrl` captured but unused (transcription dropped — caption + `locationName` sufficient).
- Billing: $2.60 / 1,000 reels. Free tier $5 credit is enough for hackathon.

Hard-won learnings (do not regress):

- `ModelSettings(tool_choice="required", parallel_tool_calls=True)` on `_extract_for_reel` — without `required`, model sometimes skips `WebSearchTool` and hallucinates coords.
- `_MODEL_ERRORS = (openai.NotFoundError, openai.BadRequestError, openai.PermissionDeniedError)` — typed fallback to `gpt-4o`. Apply to BOTH scraper and extractor.
- `output_type` must be a Pydantic model, not a bare list: use `ExtractionResult(places: list[PlaceResult])`.
- Pydantic `lat/lng` bounds: `ge=-90, le=90`, `ge=-180, le=180` — catches hallucinated coords.
- `evidence_caption_quote` must be a verbatim substring of `caption + locationName` — drop the place otherwise.
- `WebSearchTool` calls appear as `ToolSearchCallItem` in SDK `new_items`, NOT `ToolCallItem` — match both class-name patterns when counting tool calls.

### Gate 1 tolerance (live vs cache)

`spike_planner.py:_verify_searches` is a soft gate, not a strict one — the LLM legitimately batches TASK A's per-place searches when ``_MAX_PLACES=5`` so the observed `web_search` count drifts below the naive `expected` value. Module-level ``_SEARCH_GATE_TOLERANCE = 2`` defines the slack; ``floor = max(3, expected - _SEARCH_GATE_TOLERANCE)``.

Three tiers:
- ``count >= expected``: silent pass.
- ``expected > count >= floor``: log a warning, return the live result anyway (absorbs batched TASK A).
- ``count < floor``: raise ``RuntimeError`` — `main.py` catches it and serves `data/planner_output.json` with ``"source": "cache"`` (guardrail #1).

Empirical signal: live runs at the ``_MAX_PLACES=5`` cap are the batching danger zone — 5 place searches collapsed into 3 parallel calls yielded 5 web_search calls vs the strict gate's 7, which used to force cache on every live run. Operationally: warnings on stage are noise — the floor is the actual breaker. Only escalate if ``RuntimeError`` rate climbs.

---

## Weather Agent (`spike_weather.py`)

```python
class DayForecast(BaseModel):
    date: str                # YYYY-MM-DD
    temp_min_c: float
    temp_max_c: float
    precipitation_mm: float
    summary: str             # one sentence: "Light rain, 14-19°C"

class WeatherReport(BaseModel):
    destination: str
    day_forecasts: list[DayForecast]
```

One `function_tool` (`fetch_weather`) calls `GET https://api.open-meteo.com/v1/forecast` with `daily=temperature_2m_max,temperature_2m_min,precipitation_sum&forecast_days=7`. Free, no auth, 10k calls/day non-commercial.

Agent:
```python
weather_agent = Agent(
    name="weather_agent",
    model="gpt-5.5-2026-04-23",
    tools=[fetch_weather],
    output_type=WeatherReport,
)
```

Wire-up: runs in parallel with `enricher` via `asyncio.gather` in `_run_planner_inner`. Result merged into `EnrichedContext.weather_report` (replaces free-text `weather_summary`).

**Fallback**: on 5xx or 8s timeout, return `WeatherReport(destination=<city>, day_forecasts=[])`. Pipeline never blocks.

---

## Hotel Recommendation — 3 + best pick (`spike_hotel_base.py`)

The hotel-base optimizer returns **exactly 3 hotel candidates**, all within the chosen base area, and flags the **single best** one via `selected_hotel_id` (the hotel that fulfills ALL the traveler's requirements — budget, walkability, station access, preferences).

```python
_MAX_HOTELS = 3   # was 2 — itinerary shows 3 recs + best pick

class HotelCandidate(BaseModel):
    id: str
    name: str
    base_area_id: str          # MUST equal selected_base.id (enforced on normalize)
    lat: float | None; lng: float | None
    price_summary: str
    booking_url: str | None
    rationale: str
    tradeoffs: list[str]

class HotelBaseResult(BaseModel):
    source: Literal["live", "cache"]
    selected_base: BaseAreaCandidate
    base_areas: list[BaseAreaCandidate]
    hotel_candidates: list[HotelCandidate]   # exactly 3
    selected_hotel_id: str                   # the best pick — one of the 3
```

Invariants (enforced in `normalize_live_hotel_base_result`, `build_fallback_hotel_base_result`, AND on cache load):
- Exactly 3 `hotel_candidates`. Live under-returns → pad deterministically; over-returns → truncate (always keeping `selected_hotel_id`).
- Every `hotel_candidates[].base_area_id == selected_base.id`.
- `selected_hotel_id` is always one of the 3.

Surfacing into the itinerary: `_run_planner_inner` maps the 3 candidates into `ItineraryOutput.hotel_options: list[HotelOption]` (one with `is_best=True`). The daily `ItineraryDay.hotel` and `recommended_hotel` stay the single best pick (Gate 6 unchanged).

---

## Booking + Agentic Payment (`spike_booking.py`)

Bookings are **mock fulfillment** (deep links). The new headline is the **agentic payment**: AP2 authorization + x402 settlement, modeled behind a `PaymentProvider` seam so Zhi Hao can drop in a real client without touching the booking flow.

```python
class PaymentSettlement(BaseModel):              # NEW — the "real payment" record (separate from booking)
    settlement_id: str                           # "ap2-mock-{sha1[:10]}" (mock) | real x402 tx ref
    payment_protocol: Literal["ap2_x402"] = "ap2_x402"
    payment_network: str = "mock"                # "mock" | "base-sepolia" | "base"
    payment_status: Literal["mock", "pending", "settled", "failed"] = "mock"
    amount_sgd: float | None = None
    is_mock_settlement: bool = True              # True this round; False when real x402 settles
    notes: str = ""

class BookingItem(BaseModel):
    booking_id: str                              # "TC-MOCK-{sha1[:8]}" (mock) | "ord_..." (deprecated Duffel)
    category: Literal["flight", "hotel", "attraction"]
    name: str
    price_estimate_sgd: float | None
    status: Literal["confirmed", "reserved"]     # FULFILLMENT, not payment
    book_url: str
    source: Literal["duffel_sandbox", "booking_deeplink", "klook_deeplink"]   # UNCHANGED union
    is_mock: bool                                # ALWAYS True (fulfillment is simulated)
    notes: str
    settlement: PaymentSettlement | None = None  # NEW — the agentic-payment record

class BookingResult(BaseModel):
    items: list[BookingItem]
    total_estimate_sgd: float
    is_mock: bool = True
    payment_protocol: str = "ap2_x402"           # NEW
    total_settled_sgd: float = 0.0               # NEW
    is_mock_settlement: bool = True              # NEW
```

The `PaymentProvider` seam:

```python
class PaymentProvider(ABC):
    async def settle(self, *, reference, amount_sgd, category, name) -> PaymentSettlement: ...

class MockSettlementProvider(PaymentProvider):   # default — deterministic, NO network
    # payment_status="mock", is_mock_settlement=True, settlement_id="ap2-mock-{hash}"
    ...
```

`book_trip(..., payment_provider: PaymentProvider | None = None)` defaults to `MockSettlementProvider`. After the deep-link `BookingItem`s are assembled + invariant-sanitized, the provider's `settle()` is called per item (timeout-bound, never raises) and attached as `item.settlement`. **Zhi Hao's real provider** = an AP2 client (build + sign Intent/Cart mandates) → x402 client (HTTP-402 → `X-PAYMENT` → CDP facilitator settles testnet USDC) returning `payment_status="settled"`, `is_mock_settlement=False`, real `settlement_id`. The booking items stay `is_mock=True`.

Booking tools (deep-link composers, unchanged shape):

| Tool | Backend | Returns |
|---|---|---|
| `book_flight(origin, destination, date)` | Skyscanner deep-link composer (default). *Duffel sandbox only if `DUFFEL_TEST_TOKEN` set — DEPRECATED* | `BookingItem(source="booking_deeplink", status="reserved", booking_id="TC-MOCK-{hash}")` (or `duffel_sandbox`/`confirmed` on the deprecated path) |
| `book_hotel(city, checkin, checkout, guests)` | Booking.com URL composer | `BookingItem(source="booking_deeplink", status="reserved", booking_id="TC-MOCK-{hash}")` |
| `book_attraction(name, city)` | Klook URL composer | `BookingItem(source="klook_deeplink", status="reserved", booking_id="TC-MOCK-{hash}")` |

`TC-MOCK` id formula: `"TC-MOCK-" + sha1(f"{category}|{name}|{date}").hexdigest()[:8]` — deterministic, replayable, idempotent.

Wire-up: `booking_agent` runs in parallel with `narrator_agent` (both depend only on `enriched`). Result merged into `ItineraryOutput.bookings`.

**Non-negotiables**:
- `is_mock=True` on EVERY `BookingItem` — fulfillment is always simulated.
- **Payment ≠ fulfillment.** `status` (`reserved`/`confirmed`) is fulfillment; the agentic payment lives ONLY in `settlement`. `status="confirmed"` is reserved for the deprecated `duffel_sandbox` path; all mock deep-link items are `"reserved"`.
- While `is_mock_settlement=True`, `payment_status` MUST be `"mock"` (never `"settled"`) — don't let the demo claim a settlement that didn't happen.
- All payment env vars optional; `MockSettlementProvider` needs no network and never blocks the pipeline. `settle()` timeout-bound and never raises.
- `source` union is FROZEN (`duffel_sandbox`/`booking_deeplink`/`klook_deeplink`). The payment rail lives in `settlement.payment_protocol`, not `source`.
- Duffel is DEPRECATED: optional, skipped when no token; the `_test_` guard still applies when a token IS present (no production tokens).
- Pre-existing `hotel_booking_url` / `flight_booking_url` in `EnrichedContext` STAY — those are "view-this-place" links, separate from the booking/payment overlay.

---

## Non-Negotiable Demo Guardrails

1. **Cache fallback**: `data/places.json` + `data/planner_output.json` MUST be committed and pre-populated. `USE_CACHE=true` replays in seconds. The planner's soft Gate 1 (`spike_planner.py:_verify_searches`) also routes to the cached itinerary when the enricher under-searches below the floor.
2. **Hallucination guard**: every place needs `evidence_caption_quote` + `evidence_frame_index`. No evidence → drop the place.
3. **Geocoding**: extractor uses `WebSearchTool` for `lat`/`lng`. Missing coords → drop the place.
4. **Model**: `gpt-5.5-2026-04-23` primary; typed `except _MODEL_ERRORS` fallback to `gpt-4o`. No dated `gpt-4o-*` snapshots.
5. **Latency**: backend auto-falls back to cache if live extraction > 80s (`_EXTRACTION_TIMEOUT`). All `/extract` and `/itinerary` JSON responses include `"source": "live" | "cache"`.
6. **Booking + payment realism**: every `BookingItem.is_mock` MUST be `True` (fulfillment is simulated). `status` is fulfillment-only — `"confirmed"` ONLY on the deprecated `source="duffel_sandbox"` path, else `"reserved"`. Agentic payment lives in `BookingItem.settlement`; while `is_mock_settlement=True`, `payment_status` MUST be `"mock"` (never `"settled"`). Code reviewer rejects violations.
7. **Weather fallback**: Open-Meteo 5xx/timeout → return empty `day_forecasts`, never block the pipeline.
8. **Schema-parity**: any new structured field added backend-side MUST land in `frontend/lib/trip/backend-types.ts` in the same PR — **additively** (never edit/remove an existing field or union member without a matching frontend change). No orphan fields.
9. **Hotel 3-rec**: `/hotel-base` and `ItineraryOutput.hotel_options` MUST carry exactly 3 candidates with exactly one `is_best`/`selected_hotel_id`; cache load normalizes to 3.
10. **Payment env optional**: `USE_CACHE=true` (the demo path) requires NO payment, Duffel, or facilitator env var. Nothing payment-related may abort startup.

---

## PLACE_SCHEMA (strict — do not change field names)

```json
{
  "type": "object",
  "required": ["name","category","city_or_region_guess","confidence","evidence_caption_quote","evidence_frame_index"],
  "properties": {
    "name":                   {"type": "string"},
    "category":               {"type": "string", "enum": ["restaurant","hotel","attraction","transport","other"]},
    "city_or_region_guess":   {"type": "string"},
    "confidence":             {"type": "number", "minimum": 0, "maximum": 1},
    "evidence_caption_quote": {"type": "string"},
    "evidence_frame_index":   {"type": "integer"},
    "place_id":               {"type": "string"},
    "lat":                    {"type": "number"},
    "lng":                    {"type": "number"},
    "formatted_address":      {"type": "string"}
  }
}
```

Frontend `BackendExtractedPlace` mirrors this (snake_case) and does not consume `evidence_frame_index` today. Backend may serialize `-1` as a sentinel when extractor returned `None`.

---

## Build Order (day-of, do not skip steps)

1. **Skeleton up** — FastAPI + Next.js boot, demo reels env vars set
2. **Extract pipeline** end-to-end on 4 reels → commit `data/places.json` ← MUST exist before polish
3. **Planner over cache** → `data/planner_output.json` → /itinerary SSE working
4. **Mapbox map render** with extracted-place pins (Zhi Hao)
5. **Right panel SSE stream** wired (Zhi Hao)
6. **Weather + booking agents** merged into planner orchestration (this section)
7. **Stage SSE events** for demo storytelling (optional polish)
8. **Rehearse**: default `USE_CACHE=true` if anything flaky

---

## Do NOT Spend Time On

- yt-dlp or custom Instagram scraper (Apify only)
- Custom agent orchestrator (use Agents SDK)
- Instagram Graph API / OAuth
- Broad rewrites beyond the current compatibility-facade layout; keep API/SSE contracts stable
- Real booking checkout / real fulfillment / charging real money (booking is ALWAYS mock)
- Production Duffel tokens or reviving Duffel as primary (it is a deprecated optional fallback)
- Mainnet USDC / real-money x402 settlement this round (testnet only, and that's Zhi Hao's next round)
- MCP for payment / Open-Meteo (function tools + the PaymentProvider seam are simpler)
- Reverting to pop-up book / flipbook / react-pageflip / Google Maps (frontend has pivoted to a Mapbox 3D map)
- The 3D-map frontend revamp THIS round (backend-only this round; only `backend-types.ts` types are touched)
- requirements.txt (use pyproject.toml via uv)

---

## Codex Review Protocol

After writing/modifying any backend code:
```
/codex:review
```
Pass criteria: overall ≥ 7.0, no dimension ≤ 3.

---

## Day-of Hard Checkpoints

| Time | Gate |
|------|------|
| 11:30 | Skeleton running, /extract + /itinerary returning cache |
| 12:30 | Mapbox renders cached places, SSE stream visible in panel |
| 13:30 | Weather + booking agents merged, cache replay still <180s |
| 14:30 | Demo path locked, start pre-caching all images |
| 15:00 | No new features after this line |
| 17:00 | Code freeze, rehearse pitch ×5 |
