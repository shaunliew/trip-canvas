import sys
import unittest

sys.path.insert(0, "backend")

from backend.spike_planner import (  # noqa: E402
    EnrichedContext,
    PlaceInfo,
    PlaceResult,
    UserPreferences,
    _authoritative_hotel_choice,
    _build_hotel_options,
    _narrator_prompt,
)


class BuildHotelOptionsTests(unittest.TestCase):
    def test_maps_candidates_and_flags_selected_best(self):
        hotel_base = {
            "selected_hotel_id": "hotel-2",
            "hotel_candidates": [
                {"id": "hotel-1", "name": "Runner Up", "price_summary": "Budget",
                 "booking_url": "https://www.hyatt.com/h/one", "rationale": "ok",
                 "tradeoffs": ["smaller rooms"]},
                {"id": "hotel-2", "name": "Best Pick", "price_summary": "Mid",
                 "booking_url": "https://www.hyatt.com/h/two", "rationale": "best",
                 "tradeoffs": []},
                {"id": "hotel-3", "name": "Upgrade", "price_summary": "Luxury",
                 "booking_url": None, "rationale": "pricey", "tradeoffs": []},
            ],
        }
        options = _build_hotel_options(hotel_base)
        self.assertEqual(len(options), 3)
        best = [o for o in options if o.is_best]
        self.assertEqual([o.name for o in best], ["Best Pick"])

    def test_no_hotel_base_returns_empty(self):
        self.assertEqual(_build_hotel_options(None), [])

    def test_missing_selected_id_flags_first_as_best(self):
        hotel_base = {
            "selected_hotel_id": "nope",
            "hotel_candidates": [
                {"id": "h1", "name": "First"},
                {"id": "h2", "name": "Second"},
            ],
        }
        options = _build_hotel_options(hotel_base)
        self.assertTrue(options[0].is_best)
        self.assertEqual(sum(o.is_best for o in options), 1)

    def test_search_page_booking_url_is_dropped(self):
        hotel_base = {
            "selected_hotel_id": "h1",
            "hotel_candidates": [
                {"id": "h1", "name": "X",
                 "booking_url": "https://www.booking.com/searchresults.html?ss=Tokyo"},
            ],
        }
        options = _build_hotel_options(hotel_base)
        self.assertIsNone(options[0].booking_url)  # search page rejected by _clean_place_url


class PlannerHotelBaseTests(unittest.TestCase):
    def test_selected_hotel_base_candidate_is_authoritative(self):
        ctx = EnrichedContext(
            places=[PlaceInfo(name="Dotonbori", summary="Canal nightlife.")],
            recommended_hotel="Enriched Hotel",
            hotel_price_per_night="~JPY 20,000/night",
            hotel_booking_url="https://www.hyatt.com/en-US/hotel/japan/enriched-hotel",
        )
        hotel_base = {
            "selected_hotel_id": "hotel-2",
            "selected_base": {"name": "Namba", "rationale": "Central for the trip."},
            "hotel_candidates": [
                {
                    "id": "hotel-1",
                    "name": "Other Hotel",
                    "booking_url": "https://www.hyatt.com/en-US/hotel/japan/other-hotel",
                    "price_summary": "Budget",
                    "rationale": "Backup option.",
                },
                {
                    "id": "hotel-2",
                    "name": "Selected Base Hotel",
                    "booking_url": "https://www.hyatt.com/en-US/hotel/japan/selected-base-hotel",
                    "price_summary": "Mid-range",
                    "rationale": "Best base fit.",
                },
            ],
        }

        hotel_name, hotel_url, hotel_price = _authoritative_hotel_choice(ctx, hotel_base)
        prompt = _narrator_prompt(
            places=[
                PlaceResult(
                    name="Dotonbori",
                    category="attraction",
                    city_or_region_guess="Osaka",
                    confidence=0.9,
                    evidence_caption_quote="Dotonbori",
                )
            ],
            prefs=UserPreferences(start_date="2026-06-10", end_date="2026-06-12"),
            ctx=ctx,
            hotel_base=hotel_base,
        )

        self.assertEqual(hotel_name, "Selected Base Hotel")
        self.assertEqual(hotel_url, "https://www.hyatt.com/en-US/hotel/japan/selected-base-hotel")
        self.assertEqual(hotel_price, "Mid-range")
        self.assertIn("## RECOMMENDED HOTEL (single choice for the whole trip)\nSelected Base Hotel (Mid-range)", prompt)
        self.assertIn('HOTEL RULE: Set ItineraryDay.hotel = "Selected Base Hotel"', prompt)
        self.assertNotIn('HOTEL RULE: Set ItineraryDay.hotel = "Enriched Hotel"', prompt)

        hotel_base["hotel_candidates"][1]["booking_url"] = "https://www.booking.com/searchresults.html"
        hotel_name, hotel_url, _ = _authoritative_hotel_choice(ctx, hotel_base)

        self.assertEqual(hotel_name, "Selected Base Hotel")
        self.assertEqual(hotel_url, "https://www.hyatt.com/en-US/hotel/japan/enriched-hotel")

    def test_invalid_selected_hotel_preserves_enriched_hotel(self):
        ctx = EnrichedContext(
            places=[PlaceInfo(name="Dotonbori", summary="Canal nightlife.")],
            recommended_hotel="Enriched Hotel",
            hotel_price_per_night="~JPY 20,000/night",
            hotel_booking_url="https://www.hyatt.com/en-US/hotel/japan/enriched-hotel",
        )

        hotel_base = {
            "selected_hotel_id": "missing",
            "hotel_candidates": [
                {
                    "id": "hotel-1",
                    "name": "Other Hotel",
                    "booking_url": "https://www.hyatt.com/en-US/hotel/japan/other-hotel",
                }
            ],
        }

        hotel_name, hotel_url, hotel_price = _authoritative_hotel_choice(ctx, hotel_base)
        prompt = _narrator_prompt(
            places=[
                PlaceResult(
                    name="Dotonbori",
                    category="attraction",
                    city_or_region_guess="Osaka",
                    confidence=0.9,
                    evidence_caption_quote="Dotonbori",
                )
            ],
            prefs=UserPreferences(start_date="2026-06-10", end_date="2026-06-12"),
            ctx=ctx,
            hotel_base=hotel_base,
        )

        self.assertEqual(hotel_name, "Enriched Hotel")
        self.assertEqual(hotel_url, "https://www.hyatt.com/en-US/hotel/japan/enriched-hotel")
        self.assertEqual(hotel_price, "~JPY 20,000/night")
        self.assertIn('HOTEL RULE: Set ItineraryDay.hotel = "Enriched Hotel"', prompt)
        self.assertIn("No valid hotel-base selected hotel was provided.", prompt)

    def test_non_string_selected_hotel_booking_url_falls_back_to_enriched_url(self):
        ctx = EnrichedContext(
            places=[PlaceInfo(name="Dotonbori", summary="Canal nightlife.")],
            recommended_hotel="Enriched Hotel",
            hotel_price_per_night="~JPY 20,000/night",
            hotel_booking_url="https://www.hyatt.com/en-US/hotel/japan/enriched-hotel",
        )
        hotel_base = {
            "selected_hotel_id": "hotel-1",
            "hotel_candidates": [
                {
                    "id": "hotel-1",
                    "name": "Selected Base Hotel",
                    "booking_url": {"url": "https://www.hyatt.com/en-US/hotel/japan/selected-base-hotel"},
                    "price_summary": "Mid-range",
                    "rationale": "Best base fit.",
                }
            ],
        }

        hotel_name, hotel_url, hotel_price = _authoritative_hotel_choice(ctx, hotel_base)

        self.assertEqual(hotel_name, "Selected Base Hotel")
        self.assertEqual(hotel_url, "https://www.hyatt.com/en-US/hotel/japan/enriched-hotel")
        self.assertEqual(hotel_price, "Mid-range")

    def test_malformed_selected_base_does_not_crash_prompt(self):
        ctx = EnrichedContext(
            places=[PlaceInfo(name="Dotonbori", summary="Canal nightlife.")],
            recommended_hotel="Enriched Hotel",
            hotel_price_per_night="~JPY 20,000/night",
            hotel_booking_url="https://www.hyatt.com/en-US/hotel/japan/enriched-hotel",
        )
        hotel_base = {
            "selected_hotel_id": "hotel-1",
            "selected_base": "Namba",
            "hotel_candidates": [
                {
                    "id": "hotel-1",
                    "name": "Selected Base Hotel",
                    "booking_url": "https://www.hyatt.com/en-US/hotel/japan/selected-base-hotel",
                    "price_summary": "Mid-range",
                    "rationale": "Best base fit.",
                }
            ],
        }

        prompt = _narrator_prompt(
            places=[
                PlaceResult(
                    name="Dotonbori",
                    category="attraction",
                    city_or_region_guess="Osaka",
                    confidence=0.9,
                    evidence_caption_quote="Dotonbori",
                )
            ],
            prefs=UserPreferences(start_date="2026-06-10", end_date="2026-06-12"),
            ctx=ctx,
            hotel_base=hotel_base,
        )

        self.assertIn("Selected hotel: Selected Base Hotel", prompt)
        self.assertIn("Selected base: ", prompt)


if __name__ == "__main__":
    unittest.main()
