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
import logging
import time

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from backend.api.schemas import (
    DemoCacheResponse,
    ExtractRequest,
    ExtractResponse,
    HotelBaseRequest,
    ItineraryRequest,
)
from backend.api.streaming import (
    CACHE_LOAD_ERRORS as _CACHE_LOAD_ERRORS,
    HEARTBEAT_INTERVAL as _STREAMING_HEARTBEAT_INTERVAL,
    cap_hotel_base_places as _streaming_cap_hotel_base_places,
    hotel_base_stream as _streaming_hotel_base_stream,
    itinerary_stream as _streaming_itinerary_stream,
    sse_event as _streaming_sse_event,
)

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
    _load_cached_itinerary,
    _load_cached_places,
    _write_cached_places,
    run_extraction,
)
from backend.spike_planner import (
    run_planner,
)
from backend.spike_hotel_base import (
    load_cached_hotel_base_result,
    run_hotel_base_optimizer,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = _STREAMING_HEARTBEAT_INTERVAL

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
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "tripcanvas-backend"}


# ---------------------------------------------------------------------------
# /demo-cache — instant, read-only replay of all three committed caches
# ---------------------------------------------------------------------------

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
    return _streaming_sse_event(payload)


def _itinerary_stream(places, prefs, hotel_base=None):
    # SSE terminator remains "data: [DONE]\n\n".
    return _streaming_itinerary_stream(
        places,
        prefs,
        hotel_base,
        run_planner_fn=run_planner,
        load_cached_itinerary_fn=_load_cached_itinerary,
        heartbeat_interval=_HEARTBEAT_INTERVAL,
    )


def _cap_hotel_base_places(places: list[dict]) -> list[dict]:
    return _streaming_cap_hotel_base_places(places)


def _hotel_base_stream(req: HotelBaseRequest):
    return _streaming_hotel_base_stream(
        req,
        run_hotel_base_optimizer_fn=run_hotel_base_optimizer,
    )


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
