"""Tests for /itinerary stage SSE events (IMPROVEMENTS.md §3.1).

Run from repo root:
    uv run pytest backend/tests/test_itinerary_stage_events.py

The behaviour under test:
  - spike_planner._emit_stage puts a CLAUDE.md-shaped stage event onto an
    optional progress queue, and is a no-op when the queue is None.
  - main._itinerary_stream threads a progress queue into run_planner and
    forwards any queued stage events as SSE, ordered start → stage… → result → [DONE].
"""
from __future__ import annotations

import asyncio
import json
import unittest

from backend import main
from backend.spike_e2e import PlaceResult as ExtractedPlace
from backend.spike_planner import (
    ItineraryDay,
    ItineraryOutput,
    UserPreferences,
    _emit_stage,
)


def _parse_sse(chunks: list[str]) -> list[dict | str]:
    """Turn raw 'data: …\\n\\n' chunks into payloads ([DONE] kept as the literal string)."""
    events: list[dict | str] = []
    for chunk in chunks:
        body = chunk.removeprefix("data: ").strip()
        events.append(body if body == "[DONE]" else json.loads(body))
    return events


async def _drain(agen) -> list[str]:
    return [chunk async for chunk in agen]


class EmitStageTest(unittest.TestCase):
    def test_emits_claude_md_shaped_event(self) -> None:
        q: asyncio.Queue = asyncio.Queue()
        _emit_stage(q, "weather", "Fetching live forecast…")
        self.assertEqual(
            q.get_nowait(),
            {"type": "stage", "stage": "weather", "msg": "Fetching live forecast…"},
        )

    def test_none_queue_is_noop(self) -> None:
        # Must not raise when no progress channel is wired (backward compatible).
        _emit_stage(None, "weather", "ignored")


class ItineraryStreamStageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._place = ExtractedPlace.model_validate({
            "name": "Tokyo Dream Park",
            "category": "attraction",
            "city_or_region_guess": "Tokyo",
            "confidence": 0.95,
            "evidence_caption_quote": "Tokyo Dream Park",
        })
        self._prefs = UserPreferences(start_date="2026-06-10", end_date="2026-06-10")
        self._result = ItineraryOutput(
            title="Tokyo Test",
            days=[ItineraryDay(day_number=1, date="2026-06-10", activities="a", narration="n")],
            source_places=["Tokyo Dream Park"],
            source="live",
        )

    def test_stream_forwards_stage_events_from_planner(self) -> None:
        async def fake_run_planner(places, prefs, hotel_base=None, progress=None):
            # Simulate the two real planner phase boundaries.
            _emit_stage(progress, "research", "Researching places + live weather…")
            _emit_stage(progress, "narrator", "Composing itinerary + bookings…")
            return self._result

        original = main.run_planner
        main.run_planner = fake_run_planner
        try:
            chunks = asyncio.run(_drain(main._itinerary_stream([self._place], self._prefs)))
        finally:
            main.run_planner = original

        events = _parse_sse(chunks)
        types = [e["type"] if isinstance(e, dict) else e for e in events]

        # Stream contract: starts with start, ends with result then [DONE].
        self.assertEqual(types[0], "start")
        self.assertEqual(types[-2], "result")
        self.assertEqual(types[-1], "[DONE]")

        # Both planner stage events must be forwarded, before the result.
        stages = [e for e in events if isinstance(e, dict) and e["type"] == "stage"]
        self.assertEqual([s["stage"] for s in stages], ["research", "narrator"])
        result_idx = types.index("result")
        stage_idxs = [i for i, t in enumerate(types) if t == "stage"]
        self.assertTrue(all(i < result_idx for i in stage_idxs))

    def test_stage_events_drained_in_loop_while_planner_runs(self) -> None:
        """Stage events emitted mid-flight are surfaced during the wait, not only at the end.

        Drives the in-loop drain path: the planner stays alive across a heartbeat
        tick between the two stage emissions, so the stream must interleave a
        heartbeat and still deliver both stages before the result.
        """
        async def slow_run_planner(places, prefs, hotel_base=None, progress=None):
            _emit_stage(progress, "research", "phase 1")
            await asyncio.sleep(0.06)  # > patched heartbeat ⇒ forces an in-loop drain + heartbeat
            _emit_stage(progress, "narrator", "phase 2")
            await asyncio.sleep(0.02)
            return self._result

        original_run = main.run_planner
        original_hb = main._HEARTBEAT_INTERVAL
        main.run_planner = slow_run_planner
        main._HEARTBEAT_INTERVAL = 0.02
        try:
            chunks = asyncio.run(_drain(main._itinerary_stream([self._place], self._prefs)))
        finally:
            main.run_planner = original_run
            main._HEARTBEAT_INTERVAL = original_hb

        events = _parse_sse(chunks)
        types = [e["type"] if isinstance(e, dict) else e for e in events]
        stages = [e["stage"] for e in events if isinstance(e, dict) and e["type"] == "stage"]

        self.assertEqual(stages, ["research", "narrator"])
        self.assertIn("heartbeat", types)  # proves the planner was still running mid-drain
        self.assertEqual(types[-2:], ["result", "[DONE]"])
        # The first stage must land before the result (delivered mid-flight, not just flushed).
        self.assertLess(types.index("stage"), types.index("result"))


if __name__ == "__main__":
    unittest.main()
