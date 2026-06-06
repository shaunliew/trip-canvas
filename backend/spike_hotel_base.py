"""Hotel-base optimizer for TripCanvas.

This module evaluates where the user should stay after Reel extraction and
before itinerary planning. It follows the repo's flat hackathon layout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Literal, Optional

import openai
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

load_dotenv(find_dotenv())

from agents import Agent, AgentOutputSchema, ModelSettings, Runner, RunResult, WebSearchTool

logger = logging.getLogger(__name__)

_MODEL_ERRORS = (openai.NotFoundError, openai.BadRequestError, openai.PermissionDeniedError)
_HOTEL_BASE_TIMEOUT = 80.0
_MAX_BASE_AREAS = 4
_MAX_HOTELS = 3  # itinerary shows 3 hotel recommendations + 1 best pick (selected_hotel_id)


class HotelPreferenceInput(BaseModel):
    chips: list[str] = Field(default_factory=list)
    free_text: str = ""
    optimize_for_me: bool = False


class BaseAreaCandidate(BaseModel):
    id: str
    name: str
    score: int = Field(ge=0, le=100)
    center: dict[str, float]
    transit_summary: str
    rationale: str
    tradeoffs: list[str] = Field(default_factory=list)


class HotelCandidate(BaseModel):
    id: str
    name: str
    base_area_id: str
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    price_summary: str
    booking_url: Optional[str] = None
    rationale: str
    tradeoffs: list[str] = Field(default_factory=list)


class HotelBaseResult(BaseModel):
    source: Literal["live", "cache"]
    selected_base: BaseAreaCandidate
    base_areas: list[BaseAreaCandidate]
    hotel_candidates: list[HotelCandidate]
    selected_hotel_id: str


class HotelBaseAgentOutput(BaseModel):
    selected_base: BaseAreaCandidate
    base_areas: list[BaseAreaCandidate]
    hotel_candidates: list[HotelCandidate]
    selected_hotel_id: str


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def cache_path() -> str:
    return os.path.join(os.path.dirname(__file__), "data", "hotel_base_output.json")


def load_cached_hotel_base_result() -> Optional[HotelBaseResult]:
    path = cache_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    result = HotelBaseResult.model_validate(data)
    # Normalize a possibly-stale cache (e.g. an older 2-hotel file) to exactly 3.
    normalized_hotels, selected_hotel_id = _normalize_hotel_candidates(
        result.selected_base, result.hotel_candidates, result.selected_hotel_id
    )
    return result.model_copy(update={
        "source": "cache",
        "hotel_candidates": normalized_hotels,
        "selected_hotel_id": selected_hotel_id,
    })


def write_cached_hotel_base_result(result: HotelBaseResult) -> None:
    path = cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(result.model_dump_json(indent=2))


def build_hotel_base_prompt(
    places: list[dict[str, Any]],
    preferences: dict[str, Any],
    hotel_preferences: HotelPreferenceInput,
) -> str:
    place_lines = "\n".join(
        (
            f"- {p.get('name')} ({p.get('category')}, {p.get('city_or_region_guess')}): "
            f"lat={p.get('lat')}, lng={p.get('lng')}, evidence={p.get('evidence_caption_quote')!r}"
        )
        for p in places
    )
    chips = hotel_preferences.chips or ["shortest_travel", "near_station", "best_value"]
    return f"""\
You are TripCanvas' hotel-base optimizer. Choose where the traveler should stay
after their Instagram Reels have been grounded into real places.

Return exactly {_MAX_BASE_AREAS} base_areas and exactly {_MAX_HOTELS} hotel_candidates.
ALL {_MAX_HOTELS} hotel_candidates MUST belong to the selected_base (use selected_base.id
as their base_area_id). Then set selected_hotel_id to the SINGLE BEST hotel — the one
that fulfills ALL of the traveler's requirements (budget fit, walkability, station access,
and the stated preferences). The other {_MAX_HOTELS - 1} are strong runner-up options the
traveler can compare against the best pick.

Score base areas by:
- travel efficiency to the extracted places
- station access
- budget fit
- user hotel preferences
- neighborhood fit
- practical late-night food and convenience access

For each hotel candidate, make rationale explain how well it meets the requirements, and
tradeoffs explain what it gives up versus the best pick. Do not expose hidden chain-of-thought.
Use web_search for current hotel/base information. Do not invent booking URLs.

Trip preferences:
{json.dumps(preferences, ensure_ascii=False)}

Hotel preferences:
chips={json.dumps(chips, ensure_ascii=False)}
free_text={hotel_preferences.free_text or ""}
optimize_for_me={hotel_preferences.optimize_for_me}

Extracted places:
{place_lines}
"""


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value.lower()).strip("-") or "base"


def _destination(places: list[dict[str, Any]]) -> str:
    for place in places:
        city = str(place.get("city_or_region_guess") or "").strip()
        if city:
            return city
    return "Destination"


def _center(places: list[dict[str, Any]]) -> dict[str, float]:
    valid = [
        (float(p["lat"]), float(p["lng"]))
        for p in places
        if isinstance(p.get("lat"), (int, float)) and isinstance(p.get("lng"), (int, float))
    ]
    if not valid:
        return {"lat": 35.6812, "lng": 139.7671}
    return {
        "lat": sum(lat for lat, _ in valid) / len(valid),
        "lng": sum(lng for _, lng in valid) / len(valid),
    }


def _pad_hotel(base_area_id: str, center: dict[str, float], idx: int) -> HotelCandidate:
    """Deterministic filler hotel so candidate lists always reach _MAX_HOTELS."""
    labels = ["Transit Base Hotel", "Quiet Value Hotel", "Walkable Comfort Hotel"]
    label = labels[(idx - 1) % len(labels)]
    return HotelCandidate(
        id=f"{base_area_id}-hotel-{idx}",
        name=f"{base_area_id.replace('-', ' ').title()} {label}",
        base_area_id=base_area_id,
        lat=center.get("lat"),
        lng=center.get("lng"),
        price_summary="Mid-range fallback",
        booking_url=None,
        rationale="Deterministic fallback option to complete the 3-hotel shortlist.",
        tradeoffs=["Exact live price/coordinates unavailable for this fallback entry."],
    )


def _normalize_hotel_candidates(
    selected_base: BaseAreaCandidate,
    hotel_candidates: list[HotelCandidate],
    selected_hotel_id: str,
) -> tuple[list[HotelCandidate], str]:
    """Return exactly _MAX_HOTELS candidates, all in selected_base, best pick first.

    Invariants enforced (Codex plan-review recs):
      - exactly _MAX_HOTELS candidates,
      - every base_area_id == selected_base.id,
      - selected_hotel_id is one of the returned candidates.
    Under-returns are padded deterministically; over-returns are truncated while
    always keeping the selected hotel.
    """
    base_id = selected_base.id
    center = selected_base.center or {}

    # Pick the best hotel (selected_hotel_id), else fall back to the first candidate.
    selected = next((h for h in hotel_candidates if h.id == selected_hotel_id), None)
    if selected is None and hotel_candidates:
        selected = hotel_candidates[0]

    if selected is None:
        # No candidates at all — synthesize the full shortlist.
        padded = [_pad_hotel(base_id, center, i) for i in range(1, _MAX_HOTELS + 1)]
        return padded, padded[0].id

    # Best pick first, then the rest (deduped by id), all reassigned to the selected base.
    ordered: list[HotelCandidate] = [selected]
    seen = {selected.id}
    for h in hotel_candidates:
        if h.id not in seen:
            ordered.append(h)
            seen.add(h.id)
    ordered = [h.model_copy(update={"base_area_id": base_id}) for h in ordered][:_MAX_HOTELS]

    # Pad if the model under-returned.
    idx = 1
    while len(ordered) < _MAX_HOTELS:
        pad = _pad_hotel(base_id, center, idx)
        idx += 1
        if pad.id in seen:
            continue
        ordered.append(pad)
        seen.add(pad.id)

    return ordered, ordered[0].id


def build_fallback_hotel_base_result(
    places: list[dict[str, Any]],
    hotel_preferences: HotelPreferenceInput,
) -> HotelBaseResult:
    destination = _destination(places)
    center = _center(places)
    base_id = _slug(f"{destination} central base")
    selected_base = BaseAreaCandidate(
        id=base_id,
        name=f"Central {destination}",
        score=78,
        center=center,
        transit_summary="Fallback base near the extracted-place centroid; live base scoring unavailable.",
        rationale=(
            "This fallback keeps the hotel close to the center of the extracted places "
            "and uses the default optimization: shortest travel, station access, and good value."
        ),
        tradeoffs=["Live neighborhood and hotel search was unavailable for this run."],
    )
    hotel_candidates = [
        HotelCandidate(
            id=f"{base_id}-hotel-1",
            name=f"{destination} Transit Base Hotel",
            base_area_id=base_id,
            lat=center["lat"],
            lng=center["lng"],
            price_summary="Mid-range fallback",
            booking_url=None,
            rationale="Best fallback for station access and average travel distance.",
            tradeoffs=["Exact live room price unavailable."],
        ),
        HotelCandidate(
            id=f"{base_id}-hotel-2",
            name=f"{destination} Quiet Value Hotel",
            base_area_id=base_id,
            lat=None,
            lng=None,
            price_summary="Value fallback",
            booking_url=None,
            rationale="Backup fallback for quieter stay preferences.",
            tradeoffs=["Coordinates and live booking URL unavailable."],
        ),
    ]
    normalized_hotels, selected_hotel_id = _normalize_hotel_candidates(
        selected_base, hotel_candidates, hotel_candidates[0].id
    )
    return HotelBaseResult(
        source="cache",
        selected_base=selected_base,
        base_areas=[selected_base],
        hotel_candidates=normalized_hotels,
        selected_hotel_id=selected_hotel_id,
    )


def normalize_live_hotel_base_result(
    selected_base: BaseAreaCandidate,
    base_areas: list[BaseAreaCandidate],
    hotel_candidates: list[HotelCandidate],
    selected_hotel_id: str,
) -> HotelBaseResult:
    selected_base_id = selected_base.id

    normalized_base_areas = [selected_base]
    normalized_base_areas.extend(
        candidate for candidate in base_areas if candidate.id != selected_base_id
    )

    normalized_hotels, normalized_selected_id = _normalize_hotel_candidates(
        selected_base, hotel_candidates, selected_hotel_id
    )

    return HotelBaseResult(
        source="live",
        selected_base=selected_base,
        base_areas=normalized_base_areas[:_MAX_BASE_AREAS],
        hotel_candidates=normalized_hotels,
        selected_hotel_id=normalized_selected_id,
    )


hotel_base_agent = Agent(
    name="hotel_base_optimizer",
    model="gpt-5.5-2026-04-23",
    tools=[WebSearchTool(search_context_size="medium")],
    model_settings=ModelSettings(tool_choice="required", parallel_tool_calls=True),
    instructions=(
        "Evaluate hotel base areas and candidate hotels for a travel plan. "
        "Use web_search. Return structured output only. Keep rationale user-facing."
    ),
    output_type=AgentOutputSchema(HotelBaseAgentOutput, strict_json_schema=False),
)


async def _run_agent_with_fallback(agent: Agent, prompt: str, max_turns: int) -> RunResult:
    try:
        return await Runner.run(agent, prompt, max_turns=max_turns)
    except _MODEL_ERRORS:
        logger.warning("Model unavailable for %s; falling back to gpt-4o", agent.name)
        return await Runner.run(agent.clone(model="gpt-4o"), prompt, max_turns=max_turns)


async def run_hotel_base_optimizer(
    places: list[dict[str, Any]],
    preferences: dict[str, Any],
    hotel_preferences: HotelPreferenceInput,
) -> HotelBaseResult:
    prompt = build_hotel_base_prompt(places, preferences, hotel_preferences)
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(
            _run_agent_with_fallback(hotel_base_agent, prompt, max_turns=10),
            timeout=_HOTEL_BASE_TIMEOUT,
        )
        output = result.final_output_as(HotelBaseAgentOutput)
        live = normalize_live_hotel_base_result(
            selected_base=output.selected_base,
            base_areas=output.base_areas,
            hotel_candidates=output.hotel_candidates,
            selected_hotel_id=output.selected_hotel_id,
        )
        if len(live.hotel_candidates) != _MAX_HOTELS:
            raise RuntimeError(f"hotel_base_optimizer returned {len(live.hotel_candidates)} hotels")
        write_cached_hotel_base_result(live)
        logger.info("hotel-base live result in %.1fs", time.monotonic() - started)
        return live
    except Exception as exc:  # noqa: BLE001 - demo-safe fallback path
        logger.warning("hotel-base failed (%s); using cache/fallback", exc)
        try:
            cached = load_cached_hotel_base_result()
            if cached is not None:
                return cached
        except Exception as cache_exc:  # noqa: BLE001 - malformed cache should not break demo fallback
            logger.warning("hotel-base cache invalid (%s); using deterministic fallback", cache_exc)
        return build_fallback_hotel_base_result(places, hotel_preferences)
