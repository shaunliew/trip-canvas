# TripCanvas

AI-native travel planner — Instagram Reels → live agent research → **Mapbox 3D map** itinerary with **agentic payment** (AP2 + x402). Hackathon submission for **Sea × OpenAI Codex Hackathon, 6 June 2026, Singapore** (code freeze 17:00 SGT).

> **Pivot (2026-06-06):** TripCanvas moved off the flipbook/pop-up-book metaphor to a **Mapbox 3D map**, and off Duffel to an **AP2 + x402 agentic-payment seam** — the agent performs a *real* payment while the *booking stays mock*. The itinerary now surfaces **3 hotel recommendations + a best pick**. See [CLAUDE.md](CLAUDE.md) for the backend contracts and [AGENTS.md](AGENTS.md) for agent guidance.

---

## Current State (2026-06-06)

| Phase | What | Status |
|---|---|---|
| 0 | Apify MCP integration (`backend/spike.py`) | ✅ |
| 0.5 | Reels → places extraction (`backend/spike_e2e.py`) | ✅ 4 reels, 9 places, ALL 7 gates pass |
| 1.5 | Places → itinerary planner (`backend/spike_planner.py`) | ✅ ALL 6 gates pass, live URLs |
| 2 | Unified e2e + planner driver (`backend/spike_e2e_planner.py`) | ✅ Codex 7.4/10 PASS, both cache + live paths work |
| 4 | FastAPI `/extract` + `/itinerary` SSE (`backend/main.py`) | ✅ Codex 8.6/10 PASS, SSE contract verified |
| 4.5 | Hotel-base optimizer `/hotel-base` (3 recs + best pick) | ✅ `_MAX_HOTELS=3`, surfaced into `hotel_options` |
| 5 | Agentic payment seam — AP2 + x402 (`spike_booking.py`) | 🟡 mock seam this round (`MockSettlementProvider`); real client = Zhi Hao next round |
| 6 | **Mapbox 3D map** render with extracted-place pins (Shaun) | ⏳ next round (frontend revamp) |
| 7 | 3D map → streaming AI agent panel (Shaun) | ⏳ next round |

---

## Quick Start

### 1. Install + boot

```bash
uv sync                                              # install deps
uv run uvicorn backend.main:app --port 8000          # start FastAPI server
```

Health: `curl http://localhost:8000/health` → `{"status":"ok","service":"tripcanvas-backend"}`

### 2. Run the pipeline (two equivalent ways)

#### Option A — CLI one-shot (live extraction + planning)

```bash
uv run python backend/spike_e2e_planner.py
```

- Scrapes 4 reels via Apify MCP (~215s sequential)
- Extracts places via `place_extractor` agent in parallel
- Caps to top 5 by confidence (planner enricher budget)
- Runs enricher + narrator agents
- Total: **~365s end-to-end**
- Writes `backend/data/places.json` + `backend/data/planner_output.json`

#### Option B — CLI cache-only (fast, replays last extraction)

```bash
USE_CACHE=true uv run python backend/spike_e2e_planner.py
```

- Skips extraction, loads `data/places.json` (already seeded)
- Runs planner only
- Total: **~120-170s**

#### Option C — HTTP via FastAPI (frontend-facing)

```bash
# 1) Pre-extract (one-time or pre-demo). Auto-falls back to cache if extraction >80s.
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"reel_urls":["https://www.instagram.com/reel/DYbmT-SNzVK/","https://www.instagram.com/reel/DYM_I5IvLSv/","https://www.instagram.com/reel/DYGH3jFBZHz/","https://www.instagram.com/reel/DXwcVVliX3B/"]}'

# 2) Generate itinerary as SSE stream (~120-170s)
curl -N -X POST http://localhost:8000/itinerary \
  -H "Content-Type: application/json" \
  -d '{
    "preferences": {
      "start_date": "2026-06-10",
      "end_date": "2026-06-13",
      "budget_level": "mid_range",
      "free_text": "love ramen and onsen, prefer walking-friendly areas",
      "origin_city": "Singapore"
    }
  }'
```

The `/itinerary` SSE stream emits ~27 events:

```
data: {"type":"start","n_places_in":9,"n_places_used":5,"destination":"Tokyo"}
data: {"type":"heartbeat","elapsed_s":5.0}
... (24 heartbeats, one every 5s)
data: {"type":"result","content":"<ItineraryOutput JSON>","elapsed_s":122.0}
data: [DONE]
```

Frontend **must** close `EventSource` on `data: [DONE]` (NOT on a `{type:"done"}` JSON event — that's not the contract).

---

## Architecture

```
[Instagram Reels × N]
   │
   ▼  Stage 1: Apify MCP scrape (sequential, ~22s/reel)
   │
[ReelData × N]
   │
   ▼  Stage 2: place_extractor agent × N (parallel, WebSearchTool)
   │
[PlaceResult × N, deduped]
   │
   ▼  Top-5 by confidence (planner enricher budget)
   │
[ data/places.json — top 5 places ] ─────▶ frontend zooms the Mapbox 3D map
   │
   ▼  (optional) /hotel-base: hotel_base_agent → 3 hotel candidates + best pick
   │
   ▼  Stage 3: enricher agent (parallel web_search: places + hotel + flight)  ║  weather_agent (Open-Meteo)
   │
[EnrichedContext: hotel + flight + weather + per-place summaries]
   │
   ▼  Stage 4: narrator agent (ItineraryOutput JSON)  ║  booking_agent (deep links + PaymentProvider.settle → AP2/x402 mock)
   │
[ ItineraryOutput → Mapbox 3D map + streaming agent panel ]
   • hotel_options[3, one is_best]   • bookings[items, each with a mock AP2/x402 settlement]
```

### Timeout budgets (`spike_e2e_planner.py`)

| Constant | Value | Why |
|---|---:|---|
| `_EXTRACTION_TIMEOUT` | 280s | empirical: spike_e2e.py = 215s, 65s buffer |
| `_PIPELINE_TIMEOUT` | 500s | extraction 280 + planner 215 + 5s overhead |
| `_MAX_PLACES` | 5 | keeps enricher within its 155s/12-search budget |

### Three-layer cache fallback

1. `USE_CACHE=true` env → skip extraction entirely, load `data/places.json`
2. Live extraction exceeds `_EXTRACTION_TIMEOUT` OR returns empty → load `data/places.json`
3. Planner exception OR `_PIPELINE_TIMEOUT` → return last `data/planner_output.json`

Both cache files are **committed to git** as a non-negotiable demo guardrail and **self-refresh** on every successful live run.

---

## What's Verified Working (2026-05-27)

### `spike_e2e_planner.py` CLI

- **Live one-shot** (`uv run python backend/spike_e2e_planner.py`) — extraction + planning in one command, ~365s with real Apify scrape + agent run.
- **Cache path** (`USE_CACHE=true`) — 172s, replays from `data/places.json`.
- Output: 4-day Tokyo itinerary with real hotel URL, real Scoot flight URL, 5/5 real per-attraction URLs.

### FastAPI endpoints

- `GET /health` → 200 in <1s
- `POST /extract` → 200 in 81.5s (cache fallback at 80s budget), 9 places returned
- `POST /itinerary` SSE → 27 events in 122s, all SSE contract checks pass
- All 6 validation probes (empty body, missing field, enum constraints, list bounds) return clean HTTP 422
- `GET /openapi.json` exposes both endpoints with 200/422 schemas for frontend codegen

---

## Known Limitations

1. **Cache files are demo-critical**. `backend/data/places.json` and `backend/data/planner_output.json` are committed to git as the demo safety net. If you wipe them locally, run `uv run python backend/spike_e2e_planner.py` once to re-seed before the demo.
2. **Hotel choice is non-deterministic across runs** (Dormy Inn / Royal Park / Grand Hyatt have all appeared). Don't hardcode hotel names in the frontend — render the best pick from `result.recommended_hotel` and the 3 options from `result.hotel_options` (highlight the one with `is_best=true`).
3. **`_MAX_PLACES = 5` cap**. Raising this requires also bumping `_ENRICHER_TIMEOUT` in `spike_planner.py` (each extra place adds one web_search call).
4. **`backend/data/e2e_planner_output.json`** — local debug duplicate of `planner_output.json`, safe to leave untracked.
5. **No automated tests yet** — hackathon scope. Coverage relies on smoke tests + Codex peer review.
6. **FastAPI `/extract` uses the same 280s timeout as the CLI**. HTTP request can wait up to 280s before falling back to cache. Frontend should set generous timeout when calling `/extract`.

---

## Round Plan

### This round — backend (done in this PR)
- **Hotel 3-rec:** `spike_hotel_base.py` returns 3 candidates + a best pick (`selected_hotel_id`); surfaced into `ItineraryOutput.hotel_options` (one `is_best`).
- **Agentic-payment seam:** `spike_booking.py` gains a `PaymentProvider` abstraction with a default, no-network `MockSettlementProvider`. Each `BookingItem` now carries an optional `settlement` (AP2/x402 `PaymentSettlement`). Booking stays mock (`is_mock=True`); payment is a separate, swappable record.
- **Duffel deprecated:** optional fallback only (skipped when no `DUFFEL_TEST_TOKEN`); the `_test_` guard still applies when a token is set.
- **Schema-parity:** new types mirrored additively in `frontend/lib/trip/backend-types.ts` (types only — no UI yet).

### Next round — Shaun: Mapbox 3D map frontend
Rebuild the generation surface as a tilted/3D Mapbox map: globe → zoom into the extracted destination on `/extract` → place pins → streaming agent panel (consume `/itinerary` via `fetch()` streaming, close on `data: [DONE]`). Render hotels from `hotel_options` (highlight the `is_best`), and the payment overlay from `bookings[].settlement`. **Do not** revive the flipbook/pop-up book.

### Next round — Zhi Hao: real AP2 + x402 settlement
Replace `MockSettlementProvider` with a real `PaymentProvider`:
1. **AP2** — build + sign an Intent Mandate (the user's constraints) and a Cart Mandate (the specific cart), proving the human authorized the agent's purchase.
2. **x402** — request the paid resource → receive `402 Payment Required` → sign + attach the `X-PAYMENT` header → CDP facilitator verifies + settles **testnet** USDC → return `payment_status="settled"`, `is_mock_settlement=False`, real `settlement_id`.
The booking items remain `is_mock=True`; only the `settlement` becomes real. No mainnet, no real money.

### Pre-demo prep
- Default to `USE_CACHE=true` for the demo path (no payment/Duffel/facilitator env vars needed).
- Optionally re-seed live: `uv run python backend/spike_e2e_planner.py` (validates Apify quota + OpenAI auth + network), then commit the refreshed `data/*.json`.
- **One canonical itinerary result:** `backend/data/planner_output.json` is the single source of truth teammates consume — keep it to one file (no `sample_*`/`e2e_*` duplicates).

---

## Verification & Review Trail

| Item | Result |
|---|---|
| Phase 2 unified driver — Codex peer review | **7.4/10 PASS** (no dim ≤3) |
| Phase 2 — root-cause fix applied | `_EXTRACTION_TIMEOUT` 30→80→280, self-seeding cache writer |
| Phase 4 `/itinerary` endpoint — Codex peer review | **8.6/10 PASS** (no dim ≤3) |
| Phase 4 — cancellation safety fix applied | `try/finally: planner_task.cancel()` |
| End-to-end verify (`verify` skill) | **PASS** — 2 happy-path steps + 6 probes + schema check |
| Live SSE smoke test | 27 events in 122s, contract compliant |

---

## File Map

```
tripcanvas/
├── README.md                          # this file
├── pyproject.toml                     # uv-managed deps (fastapi, openai-agents, etc)
├── .env                               # OPENAI_API_KEY, APIFY_TOKEN, DEMO_REEL_URLS
├── backend/
│   ├── main.py                        # FastAPI app: /extract + /itinerary SSE
│   ├── spike.py                       # Phase 0  — Apify MCP probe
│   ├── spike_e2e.py                   # Phase 0.5 — reels → places (4 reels, 9 places verified)
│   ├── spike_planner.py               # Phase 1.5 — places → itinerary (+ hotel_options)
│   ├── spike_hotel_base.py            # hotel-base optimizer — 3 recs + best pick
│   ├── spike_booking.py               # booking deep links + PaymentProvider seam (AP2/x402; Duffel deprecated)
│   ├── spike_e2e_planner.py           # Phase 2   — unified driver, both cache + live paths work
│   └── data/                          # exactly one JSON per purpose — no duplicates
│       ├── places.json                # extraction cache (committed)
│       ├── hotel_base_output.json     # hotel-base cache (committed; 3 candidates + best pick)
│       └── planner_output.json        # THE single canonical itinerary result (committed;
│                                      #   real verified run — hotel_options + per-item AP2/x402 settlements)
└── frontend/                          # Next.js 15 + Mapbox GL JS 3D map (NOT a flipbook)
```

---

## Required Env Vars (in `.env` at project root)

```
# Required
OPENAI_API_KEY=sk-...
APIFY_TOKEN=apify_api_...

# Optional (USE_CACHE=true demo path needs none of these)
DEMO_REEL_URLS=url1,url2,url3,url4
USE_CACHE=                            # "true" to skip live extraction
BOOKING_AID=                          # optional Booking.com affiliate id

# Agentic payment (AP2 + x402) — Zhi Hao; all optional, mock by default
USE_MOCK_PAYMENT=true                 # "false" → real provider (next round)
X402_FACILITATOR_URL=                 # x402 verify+settle endpoint (CDP). Unused while mock
PAYMENT_NETWORK=mock                  # "base-sepolia" testnet | "base" | "mock"
AP2_MANDATE_SIGNING_KEY=              # AP2 Intent/Cart mandate signing key (placeholder)
X402_PAYER_ADDRESS=                   # agent wallet for testnet USDC (placeholder)

# Deprecated (optional fallback only)
DUFFEL_TEST_TOKEN=                    # if set, MUST contain "_test_"; absent → Duffel skipped

# Frontend (frontend/.env)
NEXT_PUBLIC_MAPBOX_TOKEN=...          # Mapbox GL JS token
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```
