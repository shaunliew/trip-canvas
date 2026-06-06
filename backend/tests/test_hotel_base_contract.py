import json
import unittest

from backend.spike_hotel_base import (
    BaseAreaCandidate,
    HotelBaseResult,
    HotelCandidate,
    HotelPreferenceInput,
    build_fallback_hotel_base_result,
    build_hotel_base_prompt,
    cache_path,
    hotel_base_agent,
    normalize_live_hotel_base_result,
    sse_event,
)


class HotelBaseContractTests(unittest.TestCase):
    def test_fallback_result_has_selected_base_and_three_hotels(self):
        places = [
            {
                "name": "Dotonbori",
                "category": "attraction",
                "city_or_region_guess": "Osaka",
                "lat": 34.6685,
                "lng": 135.4807,
                "confidence": 0.9,
                "evidence_caption_quote": "Dotonbori",
            },
            {
                "name": "Universal Studios Japan",
                "category": "attraction",
                "city_or_region_guess": "Osaka",
                "lat": 34.6654,
                "lng": 135.4323,
                "confidence": 0.9,
                "evidence_caption_quote": "Universal Studios Japan",
            },
        ]
        prefs = HotelPreferenceInput(
            chips=["near_station", "best_value"],
            free_text="quiet but convenient",
            optimize_for_me=False,
        )

        result = build_fallback_hotel_base_result(places, prefs)

        self.assertIsInstance(result, HotelBaseResult)
        self.assertEqual(result.source, "cache")
        self.assertGreaterEqual(len(result.base_areas), 1)
        self.assertEqual(len(result.hotel_candidates), 3)
        self.assertEqual(result.selected_base.id, result.hotel_candidates[0].base_area_id)
        self.assertEqual(result.selected_hotel_id, result.hotel_candidates[0].id)
        # Invariant: all 3 candidates belong to the selected base.
        self.assertTrue(
            all(h.base_area_id == result.selected_base.id for h in result.hotel_candidates)
        )

    def test_candidate_scores_are_bounded(self):
        candidate = BaseAreaCandidate(
            id="namba",
            name="Namba",
            score=87,
            center={"lat": 34.667, "lng": 135.500},
            transit_summary="Strong subway access to central Osaka and USJ transfers.",
            rationale="Best balance for Dotonbori, Shinsekai, and late-night food.",
            tradeoffs=["Busier at night than Umeda."],
        )

        self.assertEqual(candidate.score, 87)

    def test_hotel_candidate_accepts_unknown_coordinates(self):
        candidate = HotelCandidate(
            id="namba-value-hotel",
            name="Namba Value Hotel",
            base_area_id="namba",
            lat=None,
            lng=None,
            price_summary="Mid-range",
            booking_url=None,
            rationale="Works as a safe fallback when live search is unavailable.",
            tradeoffs=["Exact live price unavailable."],
        )

        self.assertIsNone(candidate.lat)
        self.assertIsNone(candidate.lng)

    def test_cached_fixture_preserves_selected_tokyo_hotel_recommendation(self):
        with open(cache_path(), encoding="utf-8") as fh:
            data = json.load(fh)

        result = HotelBaseResult.model_validate(data)
        selected_hotel = next(
            hotel for hotel in result.hotel_candidates if hotel.id == result.selected_hotel_id
        )

        self.assertEqual(selected_hotel.id, "hotel_royal_park_shiodome")
        self.assertEqual(selected_hotel.name, "The Royal Park Hotel Iconic Tokyo Shiodome")
        self.assertEqual(selected_hotel.lat, 35.6655)
        self.assertEqual(selected_hotel.lng, 139.7585)
        self.assertEqual(result.payment_context, None)

    def test_prompt_includes_places_and_hotel_preferences(self):
        prompt = build_hotel_base_prompt(
            places=[
                {
                    "name": "Dotonbori",
                    "category": "attraction",
                    "city_or_region_guess": "Osaka",
                    "lat": 34.6685,
                    "lng": 135.4807,
                    "confidence": 0.9,
                    "evidence_caption_quote": "Dotonbori",
                }
            ],
            preferences={
                "start_date": "2026-06-10",
                "end_date": "2026-06-13",
                "budget_level": "mid_range",
                "free_text": "love food and onsen",
                "origin_city": "Singapore",
            },
            hotel_preferences=HotelPreferenceInput(
                chips=["shortest_travel", "near_station"],
                free_text="near convenience store",
                optimize_for_me=False,
            ),
        )

        self.assertIn("Dotonbori", prompt)
        self.assertIn("shortest_travel", prompt)
        self.assertIn("near convenience store", prompt)
        self.assertIn("Return exactly", prompt)

    def test_agent_output_schema_is_runtime_loadable(self):
        schema = hotel_base_agent.output_type.json_schema()

        self.assertEqual(schema["title"], "HotelBaseAgentOutput")
        self.assertIn("hotel_candidates", schema["properties"])

    def test_sse_event_uses_data_prefix(self):
        payload = {"type": "stage", "stage": "scoring_base_areas", "msg": "Testing Namba"}
        raw = sse_event(payload)

        self.assertTrue(raw.startswith("data: "))
        self.assertTrue(raw.endswith("\n\n"))
        decoded = json.loads(raw.removeprefix("data: ").strip())
        self.assertEqual(decoded["stage"], "scoring_base_areas")

    def test_live_result_preserves_selected_base_and_hotel_when_truncated(self):
        base_areas = [
            BaseAreaCandidate(
                id=f"base-{idx}",
                name=f"Base {idx}",
                score=80 - idx,
                center={"lat": 34.6 + idx, "lng": 135.4 + idx},
                transit_summary="Transit summary",
                rationale="Rationale",
            )
            for idx in range(5)
        ]
        hotels = [
            HotelCandidate(
                id=f"hotel-{idx}",
                name=f"Hotel {idx}",
                base_area_id="base-4",
                lat=None,
                lng=None,
                price_summary="Mid-range",
                booking_url=None,
                rationale="Rationale",
            )
            for idx in range(4)  # > _MAX_HOTELS=3, forces truncation
        ]

        # selected_hotel_id="hotel-3" would be dropped by naive truncation — must survive.
        result = normalize_live_hotel_base_result(
            selected_base=base_areas[4],
            base_areas=base_areas,
            hotel_candidates=hotels,
            selected_hotel_id="hotel-3",
        )

        self.assertEqual(result.selected_base.id, "base-4")
        self.assertIn("base-4", [candidate.id for candidate in result.base_areas])
        self.assertEqual(len(result.base_areas), 4)
        self.assertEqual(result.selected_hotel_id, "hotel-3")
        self.assertEqual(result.hotel_candidates[0].id, "hotel-3")  # best pick first
        self.assertIn("hotel-3", [candidate.id for candidate in result.hotel_candidates])
        self.assertEqual(len(result.hotel_candidates), 3)
        self.assertTrue(
            all(h.base_area_id == "base-4" for h in result.hotel_candidates)
        )

    def test_live_result_uses_first_hotel_when_selected_hotel_id_is_invalid(self):
        selected_base = BaseAreaCandidate(
            id="namba",
            name="Namba",
            score=87,
            center={"lat": 34.667, "lng": 135.500},
            transit_summary="Strong subway access.",
            rationale="Best balance for the trip.",
        )
        hotels = [
            HotelCandidate(
                id="hotel-1",
                name="Hotel 1",
                base_area_id="namba",
                lat=None,
                lng=None,
                price_summary="Mid-range",
                booking_url=None,
                rationale="Rationale",
            ),
            HotelCandidate(
                id="hotel-2",
                name="Hotel 2",
                base_area_id="namba",
                lat=None,
                lng=None,
                price_summary="Mid-range",
                booking_url=None,
                rationale="Rationale",
            ),
        ]

        result = normalize_live_hotel_base_result(
            selected_base=selected_base,
            base_areas=[],
            hotel_candidates=hotels,
            selected_hotel_id="missing-hotel",
        )

        self.assertEqual(result.selected_hotel_id, "hotel-1")
        self.assertEqual(result.hotel_candidates[0].id, "hotel-1")
        self.assertEqual(result.selected_base.id, result.base_areas[0].id)
        # Under-returned (2 input) → padded deterministically to exactly 3.
        self.assertEqual(len(result.hotel_candidates), 3)
        self.assertTrue(
            all(h.base_area_id == selected_base.id for h in result.hotel_candidates)
        )


if __name__ == "__main__":
    unittest.main()
