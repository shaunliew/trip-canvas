"""Contract tests for the read-only GET /demo-cache endpoint.

/demo-cache is the instant hackathon-safe path: it replays the three committed
caches (places.json, hotel_base_output.json, planner_output.json) in ONE payload
with zero live work. These tests call the handler directly (no TestClient/httpx
dependency) — mirroring tests/test_cache_contract.py, which inserts the backend
dir onto sys.path and imports `main`.

Run from the backend/ directory:
    cd backend && uv run pytest tests/test_demo_cache_endpoint.py
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class DemoCacheHappyPathTests(unittest.TestCase):
    """Against the real committed caches — the actual demo payload."""

    def setUp(self) -> None:
        self.resp = main.demo_cache()

    def test_source_is_cache(self) -> None:
        self.assertEqual(self.resp.source, "cache")
        # Helpers stamp source="cache" on the nested payloads too.
        self.assertEqual(self.resp.hotel_base["source"], "cache")
        self.assertEqual(self.resp.itinerary["source"], "cache")

    def test_places_non_empty(self) -> None:
        self.assertIsInstance(self.resp.places, list)
        self.assertGreater(len(self.resp.places), 0)

    def test_hotel_base_has_exactly_three_candidates(self) -> None:
        self.assertEqual(len(self.resp.hotel_base["hotel_candidates"]), 3)

    def test_itinerary_has_four_days(self) -> None:
        self.assertEqual(len(self.resp.itinerary["days"]), 4)

    def test_itinerary_has_three_hotel_options_one_best(self) -> None:
        options = self.resp.itinerary["hotel_options"]
        self.assertEqual(len(options), 3)
        self.assertEqual(sum(1 for o in options if o["is_best"]), 1)

    def test_itinerary_bookings_carry_ap2_x402_settlement(self) -> None:
        items = self.resp.itinerary["bookings"]["items"]
        self.assertGreater(len(items), 0)
        for item in items:
            self.assertTrue(item["is_mock"])  # fulfillment always mock
            self.assertIsNotNone(item.get("settlement"), item["booking_id"])
            self.assertEqual(item["settlement"]["payment_protocol"], "ap2_x402")
            # Invariant: mock settlement must never claim "settled".
            if item["settlement"]["is_mock_settlement"]:
                self.assertEqual(item["settlement"]["payment_status"], "mock")

    def test_payload_is_json_serializable(self) -> None:
        # model_dump(mode="json") must round-trip cleanly to the frontend.
        json.dumps(self.resp.model_dump(mode="json"))

    def test_itinerary_days_carry_three_stops(self) -> None:
        # Structured per-day stops must flow through /demo-cache to the frontend.
        for day in self.resp.itinerary["days"]:
            stops = day["stops"]
            self.assertEqual(len(stops), 3, day["date"])
            times = [s["time_of_day"] for s in stops]
            self.assertEqual(len(set(times)), 3, times)
            for stop in stops:
                self.assertTrue(stop["name"])
                self.assertIn("category", stop)

    def test_source_places_anchored_in_stops(self) -> None:
        # Every source place appears as an anchor stop exactly once across days.
        from collections import Counter

        anchors = Counter(
            s["place_name"]
            for day in self.resp.itinerary["days"]
            for s in day["stops"]
            if s.get("place_name")
        )
        self.assertEqual(anchors, Counter(self.resp.itinerary["source_places"]))

    def test_payment_context_survives_endpoint(self) -> None:
        # ItineraryOutput must model payment_context so it is NOT dropped by
        # model_dump() — the agentic-payment (x402/AP2) summary reaches the frontend.
        ctx = self.resp.itinerary.get("payment_context")
        self.assertIsNotNone(ctx, "payment_context dropped from /demo-cache payload")
        self.assertEqual(ctx["payment_protocol"], "x402")
        self.assertTrue(ctx["mock_booking_only"])
        self.assertTrue(ctx["asset"])


class DemoCache503Tests(unittest.TestCase):
    """Each missing/invalid cache must surface a clean 503 (never a 500 leak)."""

    def _assert_503(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            main.demo_cache()
        self.assertEqual(ctx.exception.status_code, 503)

    def test_missing_places_raises_503(self) -> None:
        original = main._load_cached_places
        main._load_cached_places = lambda: (_ for _ in ()).throw(FileNotFoundError("no places.json"))
        try:
            self._assert_503()
        finally:
            main._load_cached_places = original

    def test_invalid_places_json_raises_503(self) -> None:
        original = main._load_cached_places
        main._load_cached_places = lambda: (_ for _ in ()).throw(KeyError("places"))
        try:
            self._assert_503()
        finally:
            main._load_cached_places = original

    def test_malformed_places_shape_typeerror_raises_503(self) -> None:
        # Valid JSON, wrong shape (e.g. top-level [] or "places": null) → TypeError,
        # which must still normalize to a clean 503 (not a 500 leak).
        original = main._load_cached_places
        main._load_cached_places = lambda: (_ for _ in ()).throw(
            TypeError("list indices must be integers")
        )
        try:
            self._assert_503()
        finally:
            main._load_cached_places = original

    def test_missing_hotel_base_raises_503(self) -> None:
        original = main.load_cached_hotel_base_result
        main.load_cached_hotel_base_result = lambda: None
        try:
            self._assert_503()
        finally:
            main.load_cached_hotel_base_result = original

    def test_invalid_hotel_base_raises_503(self) -> None:
        original = main.load_cached_hotel_base_result
        main.load_cached_hotel_base_result = lambda: (_ for _ in ()).throw(
            json.JSONDecodeError("bad", "doc", 0)
        )
        try:
            self._assert_503()
        finally:
            main.load_cached_hotel_base_result = original

    def test_missing_itinerary_raises_503(self) -> None:
        original = main._load_cached_itinerary
        main._load_cached_itinerary = lambda: None
        try:
            self._assert_503()
        finally:
            main._load_cached_itinerary = original

    def test_invalid_itinerary_raises_503(self) -> None:
        # A real pydantic ValidationError from a wrong-shape itinerary cache → 503.
        from spike_planner import ItineraryOutput

        original = main._load_cached_itinerary
        main._load_cached_itinerary = lambda: ItineraryOutput.model_validate({"summary": 123})
        try:
            self._assert_503()
        finally:
            main._load_cached_itinerary = original


class DemoCacheReadOnlyTests(unittest.TestCase):
    """The endpoint must never write the cache or run live work."""

    def test_does_not_write_or_run_live_work(self) -> None:
        # Sentinel-patch every write + live-work entrypoint; demo_cache must touch none.
        calls: list[str] = []
        patched = {
            "_write_cached_places": lambda *a, **k: calls.append("write_places"),
            "run_extraction": lambda *a, **k: calls.append("run_extraction"),
            "run_hotel_base_optimizer": lambda *a, **k: calls.append("run_hotel_base_optimizer"),
            "run_planner": lambda *a, **k: calls.append("run_planner"),
        }
        originals = {name: getattr(main, name) for name in patched}
        for name, stub in patched.items():
            setattr(main, name, stub)
        try:
            main.demo_cache()
        finally:
            for name, original in originals.items():
                setattr(main, name, original)
        self.assertEqual(calls, [])


class DemoCacheHttpTests(unittest.TestCase):
    """End-to-end through the real ASGI stack (routing + serialization + status).

    Direct handler calls can't verify the registered route, FastAPI's response
    serialization, or that HTTPException becomes a real 503 wire response.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient

        cls.client = TestClient(main.app)

    def test_get_returns_200_cache_payload(self) -> None:
        resp = self.client.get("/demo-cache")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["source"], "cache")
        self.assertGreater(len(body["places"]), 0)
        self.assertEqual(len(body["hotel_base"]["hotel_candidates"]), 3)
        self.assertEqual(len(body["itinerary"]["days"]), 4)
        self.assertEqual(len(body["itinerary"]["hotel_options"]), 3)

    def test_missing_cache_returns_503_over_http(self) -> None:
        original = main._load_cached_itinerary
        main._load_cached_itinerary = lambda: None
        try:
            resp = self.client.get("/demo-cache")
        finally:
            main._load_cached_itinerary = original
        self.assertEqual(resp.status_code, 503)
        self.assertIn("itinerary", resp.json()["detail"])


class ExistingEndpointsUnchangedTests(unittest.TestCase):
    """Regression guard: /demo-cache is purely additive."""

    def test_core_routes_still_registered(self) -> None:
        paths = {route.path for route in main.app.routes}
        for expected in ("/extract", "/itinerary", "/hotel-base", "/health", "/demo-cache"):
            self.assertIn(expected, paths)

    def test_sse_done_terminator_unchanged(self) -> None:
        # The SSE [DONE] contract string must remain byte-for-byte.
        import inspect

        src = inspect.getsource(main._itinerary_stream)
        self.assertIn('"data: [DONE]\\n\\n"', src)


if __name__ == "__main__":
    unittest.main()
