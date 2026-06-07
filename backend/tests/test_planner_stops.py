"""Contract tests for structured per-day stops (DayStop / ItineraryDay.stops).

Goal being enforced: each itinerary day shows ~3 time-blocked stops instead of
reading as "one place per day". Anchors are the reel-extracted source places
(place_name set) plus the hotel; supporting stops are real nearby finds
(place_name=None). The 5 source places must each anchor EXACTLY one day.

Run from repo root:
    PYTHONPATH=.:backend uv run python -m pytest backend/tests/test_planner_stops.py -q
"""
from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from backend.spike_planner import DayStop, ItineraryDay, ItineraryOutput

_CACHE = Path(__file__).resolve().parent.parent / "data" / "planner_output.json"


class DayStopModelTests(unittest.TestCase):
    """Schema-level: additive + backward compatible."""

    def test_day_without_stops_still_validates(self) -> None:
        # Legacy payload (no `stops`) must default to [] — not raise.
        day = ItineraryDay(day_number=1, date="2026-06-10", activities="x", narration="y")
        self.assertEqual(day.stops, [])

    def test_day_with_stops_validates(self) -> None:
        day = ItineraryDay(
            day_number=1,
            date="2026-06-10",
            activities="x",
            narration="y",
            stops=[
                DayStop(time_of_day="morning", name="A", category="attraction"),
                DayStop(
                    time_of_day="afternoon",
                    name="Grand Hyatt Tokyo",
                    category="hotel",
                    place_name="Grand Hyatt Tokyo",
                ),
            ],
        )
        self.assertEqual(len(day.stops), 2)
        self.assertEqual(day.stops[1].place_name, "Grand Hyatt Tokyo")

    def test_invalid_time_of_day_rejected(self) -> None:
        with self.assertRaises(Exception):
            DayStop(time_of_day="midnight", name="A", category="attraction")

    def test_invalid_category_rejected(self) -> None:
        with self.assertRaises(Exception):
            DayStop(time_of_day="morning", name="A", category="spaceport")


class CachedItineraryStopsTests(unittest.TestCase):
    """The committed demo cache must carry the curated 3-stop days."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(_CACHE.read_text())
        cls.model = ItineraryOutput.model_validate(cls.data)

    def test_every_day_has_exactly_three_stops(self) -> None:
        for day in self.model.days:
            self.assertEqual(len(day.stops), 3, f"day {day.day_number}")

    def test_unique_time_of_day_per_day(self) -> None:
        for day in self.model.days:
            times = [s.time_of_day for s in day.stops]
            self.assertEqual(len(set(times)), len(times), f"day {day.day_number}: {times}")

    def test_source_places_anchored_exactly_once(self) -> None:
        anchors = Counter(
            s.place_name for d in self.model.days for s in d.stops if s.place_name
        )
        self.assertEqual(anchors, Counter(self.model.source_places))
        # exactly once each (no duplicates)
        self.assertTrue(all(count == 1 for count in anchors.values()))

    def test_supporting_stops_have_null_place_name(self) -> None:
        # Any stop that is NOT a known source place must have place_name None.
        source = set(self.model.source_places)
        for day in self.model.days:
            for stop in day.stops:
                if stop.name not in source:
                    self.assertIsNone(stop.place_name, f"{stop.name} should be supporting")

    def test_more_than_one_stop_per_day(self) -> None:
        # The whole point: never "one place per day".
        for day in self.model.days:
            self.assertGreater(len(day.stops), 1, f"day {day.day_number}")


if __name__ == "__main__":
    unittest.main()
