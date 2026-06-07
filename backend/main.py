"""
TripCanvas FastAPI backend — two endpoints per CLAUDE.md file structure.

Endpoints:
  POST /extract      reels → places (writes data/places.json as side effect)
  POST /itinerary    places + preferences → SSE stream → ItineraryOutput

SSE termination contract (CLAUDE.md):
  data: {"type": "result", "content": "<final JSON string>"}\\n\\n
  data: [DONE]\\n\\n

Run:
  uv run uvicorn backend.main:app --reload --port 8000

Required env vars (loaded from .env at project root):
  OPENAI_API_KEY
  APIFY_TOKEN
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from backend.spike_agentic_payments import (
    AP2HotelBookingMandateRequest,
    AP2MandateResponse,
    AgenticHotelPaymentService,
    HotelBookingRequest,
    HotelBookingResponse,
    create_ap2_hotel_booking_mandate,
)
from backend.spike_e2e import PlaceResult as ExtractedPlace
from backend.spike_e2e_planner import (
    _EXTRACTION_TIMEOUT,
    _MAX_PLACES,
    _load_cached_itinerary,
    _load_cached_places,
    _top_n_by_confidence,
    _write_cached_places,
    run_extraction,
)
from backend.spike_planner import (
    PlaceResult as PlannerPlace,
    UserPreferences,
    _GLOBAL_TIMEOUT,
    run_planner,
)
from backend.spike_hotel_base import (
    HotelBaseResult,
    HotelPreferenceInput,
    load_cached_hotel_base_result,
    run_hotel_base_optimizer,
    sse_event as hotel_base_sse_event,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 5.0  # seconds; keeps proxies + EventSource alive during the 170s planner wait

app = FastAPI(title="TripCanvas Backend", version="0.1.0")

# CORS — Next.js dev server is on :3000 by default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    reel_urls: list[str] = Field(..., min_length=1, max_length=8)


class ExtractResponse(BaseModel):
    places: list[dict]
    source: str           # "live" | "cache"
    count: int


class ItineraryRequest(BaseModel):
    preferences: UserPreferences
    places: Optional[list[dict]] = None   # if None ⇒ server loads from data/places.json
    hotel_base: Optional[dict] = None


class HotelBaseRequest(BaseModel):
    preferences: UserPreferences
    places: list[dict] = Field(..., min_length=1)
    hotel_preferences: HotelPreferenceInput = Field(default_factory=HotelPreferenceInput)


class DemoCacheResponse(BaseModel):
    """Instant hackathon-safe payload: all three committed caches in one shot.

    Read-only sibling to /extract + /itinerary — never runs live work or SSE.
    """
    source: str = "cache"
    places: list[dict]
    hotel_base: dict
    itinerary: dict


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "tripcanvas-backend"}


# ---------------------------------------------------------------------------
# /demo-cache — instant, read-only replay of all three committed caches
# ---------------------------------------------------------------------------

# Any of these from a cache file means "missing or invalid" → clean 503 (never a 500 leak).
# OSError covers missing/unreadable files (FileNotFoundError + permission errors); TypeError
# covers valid-JSON-but-wrong-shape (e.g. places.json is top-level `[]`/`null`, or
# `"places": null`) where _load_cached_places does data["places"] + iterates.
_CACHE_LOAD_ERRORS = (OSError, json.JSONDecodeError, KeyError, TypeError, ValidationError)


@app.get("/demo-cache", response_model=DemoCacheResponse)
def demo_cache() -> DemoCacheResponse:
    """Return places + hotel_base + itinerary from the committed caches in one payload.

    Pure read-only demo path: NO live extraction, hotel-base optimization, planner,
    OpenAI/Apify calls, SSE, or cache writes. Any missing/invalid cache → HTTP 503.
    """
    try:
        cached_places = _load_cached_places()
    except _CACHE_LOAD_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail=f"places cache missing or invalid: {exc}. Run /extract once to seed.",
        ) from exc

    try:
        cached_hotel_base = load_cached_hotel_base_result()
    except _CACHE_LOAD_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail=f"hotel_base cache invalid: {exc}.",
        ) from exc
    if cached_hotel_base is None:
        raise HTTPException(
            status_code=503,
            detail="hotel_base cache missing. Seed data/hotel_base_output.json.",
        )

    try:
        cached_itinerary = _load_cached_itinerary()
    except _CACHE_LOAD_ERRORS as exc:
        raise HTTPException(
            status_code=503,
            detail=f"itinerary cache invalid: {exc}.",
        ) from exc
    if cached_itinerary is None:
        raise HTTPException(
            status_code=503,
            detail="itinerary cache missing. Seed data/planner_output.json.",
        )

    return DemoCacheResponse(
        places=[p.model_dump(mode="json") for p in cached_places],
        hotel_base=cached_hotel_base.model_dump(mode="json"),
        itinerary=cached_itinerary.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# /extract — reels → places (writes cache as side effect)
# ---------------------------------------------------------------------------


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest) -> ExtractResponse:
    """Run live extraction with cache fallback.

    Honors CLAUDE.md non-negotiable #5: extraction >_EXTRACTION_TIMEOUT ⇒ cache fallback.
    """
    t0 = time.monotonic()
    try:
        places = await asyncio.wait_for(
            run_extraction(req.reel_urls), timeout=_EXTRACTION_TIMEOUT
        )
        if places:
            _write_cached_places(places)
            logger.info("/extract live: %d places in %.1fs", len(places), time.monotonic() - t0)
            return ExtractResponse(
                places=[p.model_dump(mode="json") for p in places],
                source="live",
                count=len(places),
            )
        logger.warning("/extract returned 0 places — falling back to cache")
    except asyncio.TimeoutError:
        logger.warning("/extract exceeded %.0fs — falling back to cache", _EXTRACTION_TIMEOUT)
    except Exception as exc:
        logger.error("/extract failed (%s) — falling back to cache", exc)

    try:
        cached = _load_cached_places()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Extraction failed and no cached places.json available. Run spike_e2e.py once to seed.",
        ) from exc
    return ExtractResponse(
        places=[p.model_dump(mode="json") for p in cached],
        source="cache",
        count=len(cached),
    )


# ---------------------------------------------------------------------------
# /itinerary — places → ItineraryOutput (SSE)
# ---------------------------------------------------------------------------


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _itinerary_stream(
    places: list[ExtractedPlace],
    prefs: UserPreferences,
    hotel_base: Optional[dict] = None,
):
    """Yield SSE events: start → heartbeats → result → [DONE]."""
    if not places:
        yield _sse_event({"type": "error", "message": "no places provided and cache empty"})
        yield "data: [DONE]\n\n"
        return

    # Cap places to match planner's enricher budget (Phase 2 learning).
    capped = (
        _top_n_by_confidence(places, _MAX_PLACES)
        if len(places) > _MAX_PLACES else places
    )
    planner_places = [PlannerPlace.model_validate(p.model_dump()) for p in capped]

    yield _sse_event({
        "type": "start",
        "n_places_in": len(places),
        "n_places_used": len(capped),
        "destination": planner_places[0].city_or_region_guess,
    })

    t0 = time.monotonic()
    progress: asyncio.Queue = asyncio.Queue()
    planner_task = asyncio.create_task(
        asyncio.wait_for(
            run_planner(planner_places, prefs, hotel_base=hotel_base, progress=progress),
            timeout=_GLOBAL_TIMEOUT,
        )
    )

    # Wrap heartbeat loop + result extraction in try/finally so a client disconnect
    # (generator cancellation) doesn't leak the planner task and burn OpenAI tokens.
    try:
        # Heartbeats keep the connection warm during the ~170s planner wait;
        # stage events drained from `progress` surface phase changes (research/narrator).
        while not planner_task.done():
            while not progress.empty():
                yield _sse_event(progress.get_nowait())
            try:
                await asyncio.wait_for(asyncio.shield(planner_task), timeout=_HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                yield _sse_event({
                    "type": "heartbeat",
                    "elapsed_s": round(time.monotonic() - t0, 1),
                })
            except Exception:
                # Planner errored; loop exits via done() check next iter.
                break

        # Flush any stage events emitted just before the planner finished.
        while not progress.empty():
            yield _sse_event(progress.get_nowait())

        try:
            result = planner_task.result()
        except Exception as exc:
            logger.error("/itinerary planner failed (%s) — trying cached itinerary", exc)
            cached = _load_cached_itinerary()
            if cached is None:
                yield _sse_event({"type": "error", "message": f"planner failed: {exc}"})
                yield "data: [DONE]\n\n"
                return
            result = cached

        elapsed = round(time.monotonic() - t0, 1)
        logger.info("/itinerary done in %.1fs (source=%s)", elapsed, result.source)

        # CLAUDE.md SSE contract: result first, then [DONE].
        yield _sse_event({"type": "result", "content": result.model_dump_json(), "elapsed_s": elapsed})
        yield "data: [DONE]\n\n"
    finally:
        # Client disconnect or any unwind path — cancel pending planner work.
        if not planner_task.done():
            planner_task.cancel()


def _cap_hotel_base_places(places: list[dict]) -> list[dict]:
    if len(places) <= _MAX_PLACES:
        return places
    return sorted(
        places,
        key=lambda place: -(
            place.get("confidence")
            if isinstance(place.get("confidence"), (int, float)) else 0
        ),
    )[:_MAX_PLACES]


async def _hotel_base_stream(req: HotelBaseRequest):
    capped_places = _cap_hotel_base_places(req.places)
    destination = capped_places[0].get("city_or_region_guess") or "destination"
    t0 = time.monotonic()
    yield hotel_base_sse_event({
        "type": "start",
        "destination": destination,
        "place_count": len(capped_places),
        "n_places_in": len(req.places),
        "n_places_used": len(capped_places),
    })
    yield hotel_base_sse_event({
        "type": "stage",
        "stage": "scoring_base_areas",
        "msg": "Testing hotel base areas against extracted places.",
    })
    hotel_base_task = asyncio.create_task(
        run_hotel_base_optimizer(
            places=capped_places,
            preferences=req.preferences.model_dump(mode="json"),
            hotel_preferences=req.hotel_preferences,
        )
    )
    try:
        while not hotel_base_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(hotel_base_task), timeout=_HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                yield hotel_base_sse_event({
                    "type": "heartbeat",
                    "elapsed_s": round(time.monotonic() - t0, 1),
                })
            except Exception:
                break

        try:
            result: HotelBaseResult = hotel_base_task.result()
        except Exception as exc:  # noqa: BLE001 - SSE errors must terminate cleanly
            yield hotel_base_sse_event({"type": "error", "message": f"hotel-base failed: {exc}"})
            yield "data: [DONE]\n\n"
            return

        for candidate in result.base_areas:
            yield hotel_base_sse_event({
                "type": "base_candidate",
                "candidate": candidate.model_dump(mode="json"),
            })
        yield hotel_base_sse_event({
            "type": "stage",
            "stage": "finding_hotels",
            "msg": f"Finding hotel candidates in {result.selected_base.name}.",
        })
        for candidate in result.hotel_candidates:
            yield hotel_base_sse_event({
                "type": "hotel_candidate",
                "candidate": candidate.model_dump(mode="json"),
            })
        yield hotel_base_sse_event({
            "type": "stage",
            "stage": "selecting_base",
            "msg": f"Selected {result.selected_base.name}.",
        })
        yield hotel_base_sse_event({
            "type": "result",
            "content": result.model_dump_json(),
            "elapsed_s": round(time.monotonic() - t0, 1),
        })
        yield "data: [DONE]\n\n"
    finally:
        if not hotel_base_task.done():
            hotel_base_task.cancel()


@app.post("/itinerary")
async def itinerary(req: ItineraryRequest) -> StreamingResponse:
    """Stream planning progress + final ItineraryOutput as SSE."""
    if req.places is not None:
        places = [ExtractedPlace.model_validate(p) for p in req.places]
    else:
        try:
            places = _load_cached_places()
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=503,
                detail="No places provided and no cached places.json available. Call /extract first.",
            ) from exc

    return StreamingResponse(
        _itinerary_stream(places, req.preferences, req.hotel_base),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # disable nginx buffering if proxied
        },
    )


@app.post("/hotel-base")
async def hotel_base(req: HotelBaseRequest) -> StreamingResponse:
    return StreamingResponse(
        _hotel_base_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/hotel-booking", response_model=HotelBookingResponse)
async def hotel_booking(req: HotelBookingRequest) -> HotelBookingResponse:
    return AgenticHotelPaymentService().run_payment_loop(req)


@app.post("/ap2/hotel-booking-mandate", response_model=AP2MandateResponse)
async def ap2_hotel_booking_mandate(req: AP2HotelBookingMandateRequest) -> AP2MandateResponse:
    return create_ap2_hotel_booking_mandate(req)
