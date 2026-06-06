# TripCanvas

AI-native travel planner — Instagram Reels → illustrated pop-up trip book. Hackathon submission for **Sea × OpenAI Codex Hackathon, 6 June 2026, Singapore** (code freeze 17:00 SGT).

---

## Current State (2026-05-27)

| Phase | What | Status |
|---|---|---|
| 0 | Apify MCP integration (`backend/spike.py`) | ✅ |
| 0.5 | Reels → places extraction (`backend/spike_e2e.py`) | ✅ 4 reels, 9 places, ALL 7 gates pass |
| 1.5 | Places → itinerary planner (`backend/spike_planner.py`) | ✅ ALL 6 gates pass, live URLs |
| 2 | Unified e2e + planner driver (`backend/spike_e2e_planner.py`) | ✅ Codex 7.4/10 PASS, both cache + live paths work |
| 4 | FastAPI `/extract` + `/itinerary` SSE (`backend/main.py`) | ✅ Codex 8.6/10 PASS, SSE contract verified |
| 4.5 | Map render with clustered pins (Zhi Hao) | ⏳ unblocked — has SSE contract |
| 5 | Pop-up book template (Zhi Hao) | ⏳ unblocked — has `data/planner_output.json` |
| 6 | Frontend integration (paste → spinner → book) | ⏳ blocked on Phase 4.5 + 5 |
| 7 | Hotel pin → streaming agent panel (Shaun) | ⏳ next Shaun task |

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
[ data/places.json — top 5 places ]
   │
   ▼  Stage 3: enricher agent (parallel web_search: places + hotel + weather + flight)
   │
[EnrichedContext: hotel + flight + weather + per-place summaries]
   │
   ▼  Stage 4: narrator agent (structured ItineraryOutput JSON)
   │
[ ItineraryOutput → frontend pop-up book ]
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
2. **Hotel choice is non-deterministic across runs** (Dormy Inn / Royal Park / Grand Hyatt have all appeared). Don't hardcode hotel names in the frontend — always render from `result.recommended_hotel`.
3. **`_MAX_PLACES = 5` cap**. Raising this requires also bumping `_ENRICHER_TIMEOUT` in `spike_planner.py` (each extra place adds one web_search call).
4. **`backend/data/e2e_planner_output.json`** — local debug duplicate of `planner_output.json`, safe to leave untracked.
5. **No automated tests yet** — hackathon scope. Coverage relies on smoke tests + Codex peer review.
6. **FastAPI `/extract` uses the same 280s timeout as the CLI**. HTTP request can wait up to 280s before falling back to cache. Frontend should set generous timeout when calling `/extract`.

---

## What I (Shaun) Should Do Next

### A. Hotel pin → streaming agent panel (Phase 7)

**The "wow moment" of the demo.** After the pop-up book renders, the user sees a map with pins — one pin per place, including hotels. Clicking a hotel pin opens a side panel that **streams live agent reasoning in real time** as the AI thinks about *that specific hotel*.

The audience watches the AI literally calling tools and writing text token-by-token. It feels alive instead of canned.

#### What the user sees on stage

Panel opens. Inside, text streams letter-by-letter while tool badges appear:

```
  [🔍 web_search] "Dormy Inn Ueno Okachimachi reviews 2026"
  → Found 3 results

  [🔍 web_search] "Dormy Inn Ueno onsen rooftop bath"
  → Found 5 results

  Comparing rooftop hot spring access...

  This property stands out for its rooftop onsen
  open until 2 AM, which matches your "love onsen"
  preference. Located 4 min walk from Okachimachi
  station — strong walkability score.

  [🔍 web_search] "Dormy Inn Ueno Okachimachi June 2026 rate"
  → Current rate ~JPY 26,000/night

  Recommendation: book directly via booking.com to
  lock the current rate; cancellation is free until...
```

#### How this differs from `/itinerary` (already built)

| Aspect | `/itinerary` (built) | `/agent/hotel` (Phase 7) |
|--------|---------------------|-------------------------|
| What it streams | **Stage markers** (`start`, `heartbeat`, `result`, `[DONE]`) | **Raw agent activity** (token-by-token text, tool call events, tool outputs) |
| Granularity | 4 milestones | hundreds of token-level events |
| Trigger | Initial submit ("generate my trip") | Pin click ("tell me about this hotel") |
| Backing API | `Runner.run()` + custom SSE wrapping | `Runner.run_streamed()` from Agents SDK (built-in event stream) |
| Duration | 122-170s | 5-15s typically — one focused topic |
| Demo purpose | "Plan my trip" → fast result | "Show me you're thinking" → agentic narrative |

#### Why this matters for hackathon scoring

Hackathon judges have seen 100 "AI travel planner" demos. They've seen output. They have NOT seen agents thinking in front of them in real time. This feature is the priority because it makes the agentic-AI nature **visible to the audience** — without it, the demo is indistinguishable from a static itinerary generator with prerendered results.

The OpenAI Agents SDK natively supports this via `Runner.run_streamed()`, which yields three event types you'd forward to SSE:

- `raw_response_event` — partial text tokens (gives the "ChatGPT typing" feel)
- `run_item_stream_event` — tool calls and tool outputs (gives the badges)
- `agent_updated_stream_event` — agent identity changes (handoffs)

#### Concrete sketch

```python
# backend/lib/agents/hotels.py
hotels_agent = Agent(
    name="hotels_specialist",
    model="gpt-5.5-2026-04-23",
    tools=[WebSearchTool(search_context_size="high")],
    instructions="Deep-dive on a specific hotel: amenities, reviews, location quality, current rate.",
)

# backend/main.py — new endpoint
class HotelQuery(BaseModel):
    hotel_name: str
    destination: str
    start_date: str
    end_date: str
    free_text: str = ""

@app.post("/agent/hotel")
async def hotel_agent_stream(req: HotelQuery):
    prompt = (
        f"Tell me about {req.hotel_name} in {req.destination} for stays "
        f"between {req.start_date} and {req.end_date}. User notes: {req.free_text}"
    )

    async def stream():
        result = Runner.run_streamed(hotels_agent, prompt)
        async for event in result.stream_events():
            if event.type == "raw_response_event":
                # token-level text delta
                yield f"data: {json.dumps({'type':'token','delta':event.data.delta})}\n\n"
            elif event.type == "run_item_stream_event":
                # tool call started / output received
                yield f"data: {json.dumps({'type':'tool','name':event.item.name,'status':event.item.status})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
```

**Effort:** ~1-2 hours. The agent is roughly a stripped-down copy of the enricher's hotel-search logic. The streaming wrapping is the new part — and the Agents SDK does the heavy lifting via `Runner.run_streamed()`.

**Frontend contract:** Zhi Hao's hotel-pin click handler opens `EventSource` to `POST /agent/hotel`, then renders each event as it arrives — tool badges materialize, text streams in. Close on `data: [DONE]` per the same SSE contract as `/itinerary`.

### B. Respond fast to Zhi Hao's integration questions

He has everything he needs to start the pop-up book:
- A real SSE endpoint at `POST http://localhost:8000/itinerary`
- The exact event shape (`start`, `heartbeat`, `result`, `[DONE]`)
- A real seeded itinerary in `backend/data/planner_output.json` for offline template work
- Real booking URLs to wire into "Book hotel" / "Book flight" buttons

When he hits CORS, schema, or contract issues, unblock him immediately — pop-up book is the visual differentiator.

### C. (Nice to have) `.gitignore` the debug artifact

Add `backend/data/e2e_planner_output.json` to `.gitignore` so it stops appearing in `git status`. One-line change.

### D. (Pre-demo prep) Rehearse the live path once

Once before the demo:
1. Delete `backend/data/places.json` + `backend/data/planner_output.json`
2. Run `uv run python backend/spike_e2e_planner.py`
3. Confirm completion in <500s with real URLs
4. Commit the refreshed cache files

This validates Apify quota + OpenAI auth + network conditions on the venue side.

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
│   ├── spike_planner.py               # Phase 1.5 — places → itinerary (4-day verified)
│   ├── spike_e2e_planner.py           # Phase 2   — unified driver, both cache + live paths work
│   └── data/
│       ├── places.json                # 9-place cache (committed)
│       ├── planner_output.json        # itinerary fallback (committed)
│       └── e2e_planner_output.json    # debug duplicate (untracked)
└── frontend/                          # Zhi Hao territory (Next.js + react-pageflip)
```

---

## Required Env Vars (in `.env` at project root)

```
OPENAI_API_KEY=sk-...
APIFY_TOKEN=apify_api_...
DEMO_REEL_URLS=url1,url2,url3,url4
GOOGLE_MAPS_API_KEY=...               # needed by frontend only
USE_CACHE=                            # set to "true" to skip live extraction
```
