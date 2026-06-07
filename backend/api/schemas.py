from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from backend.spike_hotel_base import HotelPreferenceInput
from backend.spike_planner import UserPreferences


class ExtractRequest(BaseModel):
    reel_urls: list[str] = Field(..., min_length=1, max_length=8)


class ExtractResponse(BaseModel):
    places: list[dict]
    source: str
    count: int


class ItineraryRequest(BaseModel):
    preferences: UserPreferences
    places: Optional[list[dict]] = None
    hotel_base: Optional[dict] = None


class HotelBaseRequest(BaseModel):
    preferences: UserPreferences
    places: list[dict] = Field(..., min_length=1)
    hotel_preferences: HotelPreferenceInput = Field(default_factory=HotelPreferenceInput)


class DemoCacheResponse(BaseModel):
    """Instant hackathon-safe payload: all three committed caches in one shot.

    Read-only sibling to /extract + /itinerary; never runs live work or SSE.
    """

    source: str = "cache"
    places: list[dict]
    hotel_base: dict
    itinerary: dict
