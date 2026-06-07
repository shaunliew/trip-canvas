from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from pydantic import ValidationError

from backend.api.schemas import HotelBaseRequest
from backend.spike_e2e import PlaceResult as ExtractedPlace
from backend.spike_e2e_planner import _MAX_PLACES, _load_cached_itinerary, _top_n_by_confidence
from backend.spike_hotel_base import (
    HotelBaseResult,
    run_hotel_base_optimizer,
    sse_event as hotel_base_sse_event,
)
from backend.spike_planner import (
    PlaceResult as PlannerPlace,
    UserPreferences,
    _GLOBAL_TIMEOUT,
    run_planner,
)

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 5.0

# Any of these from a cache file means "missing or invalid" -> clean 503.
CACHE_LOAD_ERRORS = (OSError, json.JSONDecodeError, KeyError, TypeError, ValidationError)


RunPlannerFn = Callable[
    [list[PlannerPlace], UserPreferences, Optional[dict], Optional[asyncio.Queue[dict]]],
    Awaitable[object],
]
LoadCachedItineraryFn = Callable[[], object]
RunHotelBaseOptimizerFn = Callable[..., Awaitable[HotelBaseResult]]


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def itinerary_stream(
    places: list[ExtractedPlace],
    prefs: UserPreferences,
    hotel_base: Optional[dict] = None,
    *,
    run_planner_fn: RunPlannerFn = run_planner,
    load_cached_itinerary_fn: LoadCachedItineraryFn = _load_cached_itinerary,
    heartbeat_interval: float = HEARTBEAT_INTERVAL,
):
    """Yield SSE events: start -> heartbeats/stages -> result -> [DONE]."""
    if not places:
        yield sse_event({"type": "error", "message": "no places provided and cache empty"})
        yield "data: [DONE]\n\n"
        return

    capped = _top_n_by_confidence(places, _MAX_PLACES) if len(places) > _MAX_PLACES else places
    planner_places = [PlannerPlace.model_validate(p.model_dump()) for p in capped]

    yield sse_event({
        "type": "start",
        "n_places_in": len(places),
        "n_places_used": len(capped),
        "destination": planner_places[0].city_or_region_guess,
    })

    t0 = time.monotonic()
    progress: asyncio.Queue = asyncio.Queue()
    planner_task = asyncio.create_task(
        asyncio.wait_for(
            run_planner_fn(planner_places, prefs, hotel_base=hotel_base, progress=progress),
            timeout=_GLOBAL_TIMEOUT,
        )
    )

    try:
        while not planner_task.done():
            while not progress.empty():
                yield sse_event(progress.get_nowait())
            try:
                await asyncio.wait_for(asyncio.shield(planner_task), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield sse_event({
                    "type": "heartbeat",
                    "elapsed_s": round(time.monotonic() - t0, 1),
                })
            except Exception:
                break

        while not progress.empty():
            yield sse_event(progress.get_nowait())

        try:
            result = planner_task.result()
        except Exception as exc:
            logger.error("/itinerary planner failed (%s) — trying cached itinerary", exc)
            cached = load_cached_itinerary_fn()
            if cached is None:
                yield sse_event({"type": "error", "message": f"planner failed: {exc}"})
                yield "data: [DONE]\n\n"
                return
            result = cached

        elapsed = round(time.monotonic() - t0, 1)
        logger.info("/itinerary done in %.1fs (source=%s)", elapsed, result.source)

        yield sse_event({"type": "result", "content": result.model_dump_json(), "elapsed_s": elapsed})
        yield "data: [DONE]\n\n"
    finally:
        if not planner_task.done():
            planner_task.cancel()


def cap_hotel_base_places(places: list[dict]) -> list[dict]:
    if len(places) <= _MAX_PLACES:
        return places
    return sorted(
        places,
        key=lambda place: -(
            place.get("confidence") if isinstance(place.get("confidence"), (int, float)) else 0
        ),
    )[:_MAX_PLACES]


async def hotel_base_stream(
    req: HotelBaseRequest,
    *,
    run_hotel_base_optimizer_fn: RunHotelBaseOptimizerFn = run_hotel_base_optimizer,
):
    capped_places = cap_hotel_base_places(req.places)
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
        run_hotel_base_optimizer_fn(
            places=capped_places,
            preferences=req.preferences.model_dump(mode="json"),
            hotel_preferences=req.hotel_preferences,
        )
    )
    try:
        while not hotel_base_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(hotel_base_task), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                yield hotel_base_sse_event({
                    "type": "heartbeat",
                    "elapsed_s": round(time.monotonic() - t0, 1),
                })
            except Exception:
                break

        try:
            result: HotelBaseResult = hotel_base_task.result()
        except Exception as exc:
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
