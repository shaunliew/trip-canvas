"""Unit tests for the AP2 + x402 agentic-payment seam in spike_booking.py.

These are offline/deterministic — they exercise the PaymentProvider seam and the
booking invariants WITHOUT running the booking_agent (no network, no OpenAI).

Run from the backend/ directory:
    cd backend && uv run pytest tests/test_booking_payment.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import spike_booking  # noqa: E402
from spike_booking import (  # noqa: E402
    BookingItem,
    BookingResult,
    MockSettlementProvider,
    PaymentProvider,
    PaymentSettlement,
    _enforce_settlement_invariants,
    _settle_item,
    book_trip,
)


class _LyingProvider(PaymentProvider):
    """Returns a mock settlement that wrongly claims it 'settled' — the central
    guardrail must coerce it back to 'mock' (invariant #3)."""

    async def settle(self, *, reference, amount_sgd, category, name):
        return PaymentSettlement(
            settlement_id="ap2-mock-liar",
            payment_status="settled",       # illegal while is_mock_settlement=True
            amount_sgd=amount_sgd,
            is_mock_settlement=True,
        )


def _item(**overrides) -> BookingItem:
    base = dict(
        booking_id="TC-MOCK-deadbeef",
        category="hotel",
        name="Test Hotel",
        price_estimate_sgd=123.45,
        status="reserved",
        book_url="https://www.booking.com/hotel/jp/test.html",
        source="booking_deeplink",
        is_mock=True,
        notes="test",
    )
    base.update(overrides)
    return BookingItem(**base)


class MockSettlementProviderTests(unittest.TestCase):
    def test_settle_returns_mock_ap2_x402_settlement(self) -> None:
        provider = MockSettlementProvider()
        settlement = asyncio.run(
            provider.settle(reference="TC-MOCK-abc", amount_sgd=100.0, category="hotel", name="X")
        )
        self.assertIsInstance(settlement, PaymentSettlement)
        self.assertEqual(settlement.payment_protocol, "ap2_x402")
        self.assertTrue(settlement.is_mock_settlement)
        # Invariant #3: a mock settlement must NEVER claim "settled".
        self.assertEqual(settlement.payment_status, "mock")
        self.assertNotEqual(settlement.payment_status, "settled")
        self.assertTrue(settlement.settlement_id.startswith("ap2-mock-"))
        self.assertEqual(settlement.amount_sgd, 100.0)

    def test_settlement_id_is_deterministic(self) -> None:
        provider = MockSettlementProvider()
        a = asyncio.run(provider.settle(reference="r1", amount_sgd=None, category="flight", name="N"))
        b = asyncio.run(provider.settle(reference="r1", amount_sgd=None, category="flight", name="N"))
        c = asyncio.run(provider.settle(reference="r2", amount_sgd=None, category="flight", name="N"))
        self.assertEqual(a.settlement_id, b.settlement_id)
        self.assertNotEqual(a.settlement_id, c.settlement_id)

    def test_is_a_payment_provider(self) -> None:
        self.assertIsInstance(MockSettlementProvider(), PaymentProvider)


class SettleItemTests(unittest.TestCase):
    def test_settle_item_attaches_settlement(self) -> None:
        item = _item()
        settlement = asyncio.run(_settle_item(MockSettlementProvider(), item))
        self.assertEqual(settlement.amount_sgd, item.price_estimate_sgd)
        self.assertEqual(settlement.payment_status, "mock")

    def test_settle_item_never_raises_on_provider_failure(self) -> None:
        class BoomProvider(PaymentProvider):
            async def settle(self, *, reference, amount_sgd, category, name):  # noqa: D401
                raise RuntimeError("simulated x402 facilitator outage")

        item = _item()
        settlement = asyncio.run(_settle_item(BoomProvider(), item))
        # Failure degrades to a failed mock settlement — booking is never blocked.
        self.assertEqual(settlement.payment_status, "failed")
        self.assertTrue(settlement.is_mock_settlement)


class BookingInvariantTests(unittest.TestCase):
    def test_booking_item_accepts_optional_settlement(self) -> None:
        item = _item(settlement=None)
        self.assertIsNone(item.settlement)
        settled = item.model_copy(
            update={
                "settlement": PaymentSettlement(
                    settlement_id="ap2-mock-1234567890", amount_sgd=10.0
                )
            }
        )
        self.assertEqual(settled.settlement.payment_protocol, "ap2_x402")

    def test_source_union_is_frozen(self) -> None:
        # ap2_x402 must NOT be a booking source — it lives in settlement.payment_protocol.
        with self.assertRaises(Exception):
            _item(source="ap2_x402")


class SettlementInvariantEnforcementTests(unittest.TestCase):
    def test_mock_claiming_settled_is_coerced(self) -> None:
        bad = PaymentSettlement(
            settlement_id="x", payment_status="settled", is_mock_settlement=True
        )
        fixed = _enforce_settlement_invariants(bad, _item())
        self.assertEqual(fixed.payment_status, "mock")

    def test_non_settlement_return_becomes_failed_mock(self) -> None:
        fixed = _enforce_settlement_invariants({"not": "a settlement"}, _item())
        self.assertEqual(fixed.payment_status, "failed")
        self.assertTrue(fixed.is_mock_settlement)

    def test_real_settled_is_left_untouched(self) -> None:
        real = PaymentSettlement(
            settlement_id="0xreal", payment_status="settled",
            payment_network="base-sepolia", is_mock_settlement=False,
        )
        fixed = _enforce_settlement_invariants(real, _item())
        self.assertEqual(fixed.payment_status, "settled")
        self.assertFalse(fixed.is_mock_settlement)

    def test_settle_item_coerces_lying_provider(self) -> None:
        settlement = asyncio.run(_settle_item(_LyingProvider(), _item()))
        self.assertEqual(settlement.payment_status, "mock")  # not "settled"


class BookTripAttachmentTests(unittest.TestCase):
    """Exercise the final sanitizer + settlement-attachment path in book_trip()
    without the live booking_agent, by stubbing the agent runner."""

    def _run_with_stubbed_agent(self, agent_items, provider):
        class _FakeRun:
            final_output = BookingResult(items=agent_items, total_estimate_sgd=206.2)

        async def _fake_runner(agent, prompt, max_turns):
            return _FakeRun()

        original = spike_booking._run_agent_with_fallback
        spike_booking._run_agent_with_fallback = _fake_runner
        try:
            return asyncio.run(book_trip(
                destination_city="Tokyo", start_date="2026-06-10", end_date="2026-06-13",
                recommended_hotel="H", recommended_flight="F", origin_city="Singapore",
                attractions=["A"], payment_provider=provider,
            ))
        finally:
            spike_booking._run_agent_with_fallback = original

    def test_attaches_settlement_and_enforces_invariants(self) -> None:
        # A model output that wrongly marks a klook item "confirmed" — must be demoted,
        # and a lying provider's "settled" must be coerced to "mock".
        items = [
            _item(booking_id="TC-MOCK-h", category="hotel", source="booking_deeplink", status="reserved"),
            _item(booking_id="TC-MOCK-a", category="attraction", name="A",
                  source="klook_deeplink", status="confirmed",
                  book_url="https://www.klook.com/search/?keyword=A"),
        ]
        result = self._run_with_stubbed_agent(items, _LyingProvider())

        self.assertEqual(len(result.items), 2)
        for it in result.items:
            self.assertTrue(it.is_mock)                       # fulfillment always mock
            self.assertIsNotNone(it.settlement)
            self.assertNotEqual(it.settlement.payment_status, "settled")  # coerced
        # Non-duffel "confirmed" demoted to "reserved".
        klook = next(it for it in result.items if it.category == "attraction")
        self.assertEqual(klook.status, "reserved")
        # Aggregate payment fields populated.
        self.assertEqual(result.payment_protocol, "ap2_x402")
        self.assertTrue(result.is_mock_settlement)


if __name__ == "__main__":
    unittest.main()
