"""Contract tests over the COMMITTED demo cache files (the USE_CACHE demo path).

Codex plan-review recs: model-validate the real committed JSON (not just
unit-generated fallbacks), and prove /itinerary still streams result → [DONE]
with the new hotel_options/settlement fields present.

Run from the backend/ directory:
    cd backend && uv run pytest tests/test_cache_contract.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from spike_e2e import PlaceResult as ExtractedPlace  # noqa: E402
from spike_e2e_planner import _load_cached_itinerary  # noqa: E402
from spike_hotel_base import load_cached_hotel_base_result  # noqa: E402
from spike_planner import ItineraryOutput, UserPreferences  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class PlannerCacheContractTests(unittest.TestCase):
    def test_committed_planner_output_validates(self) -> None:
        with open(os.path.join(_DATA, "planner_output.json"), encoding="utf-8") as fh:
            out = ItineraryOutput.model_validate(json.load(fh))

        # 3 hotel options, exactly one best pick, best == recommended_hotel.
        self.assertEqual(len(out.hotel_options), 3)
        best = [o for o in out.hotel_options if o.is_best]
        self.assertEqual(len(best), 1)
        self.assertEqual(best[0].name, out.recommended_hotel)

    def test_committed_bookings_carry_mock_settlement(self) -> None:
        out = _load_cached_itinerary()
        self.assertIsNotNone(out)
        self.assertIsNotNone(out.bookings)
        for item in out.bookings.items:
            self.assertTrue(item.is_mock)  # fulfillment always mock
            self.assertIsNotNone(item.settlement, f"missing settlement for {item.booking_id}")
            # Invariant: mock settlement must never claim "settled".
            if item.settlement.is_mock_settlement:
                self.assertEqual(item.settlement.payment_status, "mock")
            self.assertEqual(item.settlement.payment_protocol, "ap2_x402")


class HotelBaseCacheContractTests(unittest.TestCase):
    def test_committed_hotel_base_normalizes_to_three(self) -> None:
        result = load_cached_hotel_base_result()
        self.assertIsNotNone(result)
        self.assertEqual(len(result.hotel_candidates), 3)
        ids = [h.id for h in result.hotel_candidates]
        self.assertIn(result.selected_hotel_id, ids)
        self.assertTrue(
            all(h.base_area_id == result.selected_base.id for h in result.hotel_candidates)
        )


class CrossCacheConsistencyTests(unittest.TestCase):
    """The committed /hotel-base and /itinerary caches must tell ONE destination
    story (both Tokyo) so a cache-path demo that shows both stays coherent."""

    def test_hotel_base_best_pick_matches_itinerary_recommended_hotel(self) -> None:
        hb = load_cached_hotel_base_result()
        it = _load_cached_itinerary()
        self.assertIsNotNone(hb)
        self.assertIsNotNone(it)
        best = next(h for h in hb.hotel_candidates if h.id == hb.selected_hotel_id)
        # Same best hotel in both caches.
        self.assertEqual(best.name, it.recommended_hotel)
        # And it is the is_best option in the itinerary's hotel_options.
        it_best = [o for o in it.hotel_options if o.is_best]
        self.assertEqual([o.name for o in it_best], [it.recommended_hotel])


class ItineraryStreamOverCacheTests(unittest.TestCase):
    def test_stream_emits_result_then_done_with_hotel_options(self) -> None:
        cached = _load_cached_itinerary()
        self.assertIsNotNone(cached)

        place = ExtractedPlace.model_validate({
            "name": "Tokyo Dream Park",
            "category": "attraction",
            "city_or_region_guess": "Tokyo",
            "confidence": 0.95,
            "evidence_caption_quote": "Tokyo Dream Park",
        })
        prefs = UserPreferences(start_date="2026-06-10", end_date="2026-06-13")

        async def fake_run_planner(places, prefs, hotel_base=None, progress=None):
            return cached

        async def drain():
            return [chunk async for chunk in main._itinerary_stream([place], prefs)]

        original = main.run_planner
        main.run_planner = fake_run_planner
        try:
            chunks = asyncio.run(drain())
        finally:
            main.run_planner = original

        bodies = [c.removeprefix("data: ").strip() for c in chunks]
        # Contract: ends with result then [DONE].
        self.assertEqual(bodies[-1], "[DONE]")
        result_event = json.loads(bodies[-2])
        self.assertEqual(result_event["type"], "result")

        # The new fields survive the cache → model → SSE round-trip.
        payload = json.loads(result_event["content"])
        self.assertEqual(len(payload["hotel_options"]), 3)
        self.assertTrue(any(o["is_best"] for o in payload["hotel_options"]))
        self.assertTrue(all(b.get("settlement") for b in payload["bookings"]["items"]))


if __name__ == "__main__":
    unittest.main()
