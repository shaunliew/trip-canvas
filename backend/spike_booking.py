"""booking_agent — DEMO-SAFE bookings + agentic payment for the TripCanvas demo.

Bookings are MOCK fulfillment (deep links). The headline is the AGENTIC PAYMENT:
AP2 (Agent Payments Protocol — signed Intent/Cart mandates = authorization) +
x402 (Coinbase HTTP-402 → X-PAYMENT header → facilitator settles USDC =
settlement), modeled behind a `PaymentProvider` seam so the real client can be
dropped in without touching the booking flow.

  - Flights: Skyscanner deep-link composer (default). Duffel sandbox is a
    DEPRECATED optional fallback — used only if DUFFEL_TEST_TOKEN is set.
  - Hotels and attractions: pure URL composers (Booking.com / Klook) — no auth,
    status="reserved".
  - Payment: each BookingItem carries an optional `settlement` (PaymentSettlement)
    produced by a PaymentProvider. The default MockSettlementProvider is
    deterministic and does NO network I/O. Zhi Hao swaps in a real AP2 + x402
    provider next round.

INVARIANTS (the code reviewer will reject violations):
  1. Every BookingItem.is_mock is True (fulfillment is always simulated).
  2. PAYMENT != FULFILLMENT. status ("reserved"/"confirmed") is fulfillment;
     "confirmed" is reserved for the DEPRECATED source="duffel_sandbox" path.
     The agentic payment lives ONLY in BookingItem.settlement.
  3. While settlement.is_mock_settlement is True, payment_status MUST be "mock"
     (never "settled") — don't claim a settlement that didn't happen.
  4. DUFFEL_TEST_TOKEN, if present, MUST contain "_test_". Absent → Duffel skipped
     (no startup abort). All payment env vars are optional.

The three @function_tools NEVER raise. PaymentProvider.settle NEVER raises.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Literal, Optional
from urllib.parse import quote_plus, urlencode

import httpx
import openai
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

load_dotenv(find_dotenv())

from agents import Agent, Runner, RunResult, function_tool  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL_ERRORS = (openai.NotFoundError, openai.BadRequestError, openai.PermissionDeniedError)
_BOOKING_AGENT_TIMEOUT = 25.0  # 5 attractions x 3s + hotel 1s + flight 8s + model 6s
_DUFFEL_URL = "https://api.duffel.com"
_DUFFEL_TIMEOUT = 8.0  # combined budget for both Duffel calls
_SETTLEMENT_TIMEOUT = 8.0  # per-item PaymentProvider.settle budget (real x402 next round)

_BOOKING_AID = os.environ.get("BOOKING_AID", "").strip()

# --- Agentic payment (AP2 + x402) — all env optional; mock by default ---
_USE_MOCK_PAYMENT = os.environ.get("USE_MOCK_PAYMENT", "true").strip().lower() != "false"
_PAYMENT_NETWORK = os.environ.get("PAYMENT_NETWORK", "mock").strip() or "mock"

# --- Duffel (DEPRECATED optional fallback) ---
_DUFFEL_TOKEN = os.environ.get("DUFFEL_TEST_TOKEN", "").strip()
_DUFFEL_ENABLED = bool(_DUFFEL_TOKEN) and "_test_" in _DUFFEL_TOKEN

if _DUFFEL_TOKEN and not _DUFFEL_ENABLED:
    # Guard still enforced WHEN a token is present — never call Duffel in prod mode.
    raise RuntimeError(
        "DUFFEL_TEST_TOKEN does not contain '_test_'. Refusing to call Duffel in "
        "non-test mode. Get a test-mode token at app.duffel.com (Developer test mode)."
    )
if _DUFFEL_ENABLED:
    logger.info("DUFFEL_TEST_TOKEN set — Duffel sandbox enabled (DEPRECATED fallback path).")
else:
    logger.info("Duffel disabled (no DUFFEL_TEST_TOKEN) — book_flight uses deep-link composer.")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PaymentSettlement(BaseModel):
    """The AGENTIC-PAYMENT record (AP2 + x402) — SEPARATE from booking fulfillment.

    Mock this round (is_mock_settlement=True, payment_status="mock"). When Zhi Hao
    wires a real provider, x402 settles testnet USDC → payment_status="settled",
    is_mock_settlement=False, settlement_id = the real tx reference.
    """

    settlement_id: str                                   # "ap2-mock-{sha1[:10]}" | real x402 tx ref
    payment_protocol: Literal["ap2_x402"] = "ap2_x402"
    payment_network: str = "mock"                        # "mock" | "base-sepolia" | "base"
    payment_status: Literal["mock", "pending", "settled", "failed"] = "mock"
    amount_sgd: Optional[float] = None
    is_mock_settlement: bool = True                      # True until a real x402 settlement lands
    notes: str = ""


class BookingItem(BaseModel):
    booking_id: str
    category: Literal["flight", "hotel", "attraction"]
    name: str
    price_estimate_sgd: Optional[float] = None
    status: Literal["confirmed", "reserved"]  # FULFILLMENT, not payment
    book_url: str
    source: Literal["duffel_sandbox", "booking_deeplink", "klook_deeplink"]
    is_mock: bool  # ALWAYS True — invariant enforced at tool layer
    notes: str
    settlement: Optional[PaymentSettlement] = None  # agentic-payment record; None until settled


class BookingResult(BaseModel):
    items: list[BookingItem] = Field(default_factory=list)
    total_estimate_sgd: float = 0.0
    is_mock: bool = True
    payment_protocol: str = "ap2_x402"
    total_settled_sgd: float = 0.0
    is_mock_settlement: bool = True


# ---------------------------------------------------------------------------
# Payment seam (AP2 + x402) — swap MockSettlementProvider for a real provider
# ---------------------------------------------------------------------------


class PaymentProvider(ABC):
    """Agentic-payment seam. Implementations authorize (AP2 mandates) and settle
    (x402) a payment, returning a PaymentSettlement. MUST be timeout-bound by the
    caller and MUST NOT raise (return a failed/mock settlement instead)."""

    @abstractmethod
    async def settle(
        self,
        *,
        reference: str,
        amount_sgd: Optional[float],
        category: str,
        name: str,
    ) -> PaymentSettlement:
        ...


class MockSettlementProvider(PaymentProvider):
    """Default provider — deterministic, NO network I/O. Same inputs → same id.

    Produces a clearly-mock AP2/x402 settlement: payment_status="mock" while
    is_mock_settlement=True (invariant #3). Zhi Hao replaces this with a real
    provider that builds + signs AP2 Intent/Cart mandates and drives an x402
    HTTP-402 → X-PAYMENT → facilitator settlement over testnet USDC.
    """

    def __init__(self, payment_network: str = "mock") -> None:
        self._network = payment_network or "mock"

    async def settle(
        self,
        *,
        reference: str,
        amount_sgd: Optional[float],
        category: str,
        name: str,
    ) -> PaymentSettlement:
        settlement_id = "ap2-mock-" + hashlib.sha1(
            f"{category}|{name}|{reference}".encode("utf-8")
        ).hexdigest()[:10]
        return PaymentSettlement(
            settlement_id=settlement_id,
            payment_protocol="ap2_x402",
            payment_network=self._network,
            payment_status="mock",          # NEVER "settled" while mock (invariant #3)
            amount_sgd=amount_sgd,
            is_mock_settlement=True,
            notes=(
                "Mock AP2/x402 settlement (no funds moved). Real provider injectable "
                "via book_trip(payment_provider=...)."
            ),
        )


def _default_payment_provider() -> PaymentProvider:
    """The provider used when book_trip is called without an explicit one.

    This round always returns MockSettlementProvider (USE_MOCK_PAYMENT defaults
    true). When Zhi Hao lands the real provider, wire it here behind
    USE_MOCK_PAYMENT=false.
    """
    if _USE_MOCK_PAYMENT:
        return MockSettlementProvider(payment_network=_PAYMENT_NETWORK)
    # Real AP2 + x402 provider not wired yet — fail safe to mock so the demo never breaks.
    logger.warning("USE_MOCK_PAYMENT=false but no real provider wired yet — using mock.")
    return MockSettlementProvider(payment_network=_PAYMENT_NETWORK)


def _failed_mock_settlement(item: BookingItem, reason: str) -> PaymentSettlement:
    return PaymentSettlement(
        settlement_id="ap2-mock-failed-" + hashlib.sha1(item.booking_id.encode()).hexdigest()[:8],
        payment_network=_PAYMENT_NETWORK,
        payment_status="failed",
        amount_sgd=item.price_estimate_sgd,
        is_mock_settlement=True,
        notes=reason,
    )


def _enforce_settlement_invariants(
    settlement: object, item: BookingItem
) -> PaymentSettlement:
    """Central guardrail over ANY provider's return (incl. Zhi Hao's real one).

    The seam must not trust injected providers blindly:
      - non-PaymentSettlement → failed mock,
      - invariant #3: a mock settlement (is_mock_settlement=True) may NEVER claim
        payment_status="settled" → coerce to "mock".
    """
    if not isinstance(settlement, PaymentSettlement):
        logger.warning(
            "Provider returned %s (not PaymentSettlement) for %s; using failed mock",
            type(settlement).__name__, item.booking_id,
        )
        return _failed_mock_settlement(item, "Provider returned an invalid settlement type.")
    if settlement.is_mock_settlement and settlement.payment_status == "settled":
        logger.warning(
            "Mock settlement claimed 'settled' for %s; coercing to 'mock' (invariant #3)",
            item.booking_id,
        )
        return settlement.model_copy(update={"payment_status": "mock"})
    return settlement


async def _settle_item(
    provider: PaymentProvider, item: BookingItem
) -> PaymentSettlement:
    """Run provider.settle for one item under a wall budget. Never raises —
    returns a failed mock settlement on timeout/error so the pipeline continues.
    The provider's return is always run through _enforce_settlement_invariants."""
    try:
        settlement = await asyncio.wait_for(
            provider.settle(
                reference=item.booking_id,
                amount_sgd=item.price_estimate_sgd,
                category=item.category,
                name=item.name,
            ),
            timeout=_SETTLEMENT_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 — settlement must never break booking
        logger.warning("settle failed for %s (%s); recording failed mock settlement", item.booking_id, exc)
        return _failed_mock_settlement(item, f"Settlement unavailable ({type(exc).__name__}); booking still reserved.")
    return _enforce_settlement_invariants(settlement, item)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_booking_id(category: str, *parts: str) -> str:
    """Deterministic, replayable mock id. Same inputs -> same id."""
    key = "|".join([category, *parts])
    return "TC-MOCK-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


def _booking_com_url(city: str, checkin: str, checkout: str, guests: int) -> str:
    params: dict[str, Any] = {
        "ss": city,
        "checkin": checkin,
        "checkout": checkout,
        "group_adults": guests,
        "no_rooms": 1,
    }
    if _BOOKING_AID:
        params["aid"] = _BOOKING_AID
    return f"https://www.booking.com/searchresults.html?{urlencode(params)}"


def _klook_url(name: str) -> str:
    return f"https://www.klook.com/search/?keyword={quote_plus(name)}"


def _skyscanner_fallback_url(origin_iata: str, destination_iata: str, departure_date: str) -> str:
    # Skyscanner uses YYMMDD; used only as a Duffel fallback deep link.
    date_compact = departure_date.replace("-", "")[2:]
    return (
        f"https://www.skyscanner.com/transport/flights/"
        f"{origin_iata.lower()}/{destination_iata.lower()}/{date_compact}/"
    )


def _flight_deeplink_dict(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    estimated_price_sgd: Optional[float],
    note: str,
) -> dict[str, Any]:
    # NOTE: Skyscanner URL maps to source="booking_deeplink" because the source
    # enum has no skyscanner_deeplink slot — this is the umbrella for non-Duffel
    # non-Klook deep links.
    return {
        "booking_id": _mock_booking_id("flight", origin_iata, destination_iata, departure_date),
        "category": "flight",
        "name": f"{origin_iata}->{destination_iata} ({departure_date})",
        "price_estimate_sgd": estimated_price_sgd,
        "status": "reserved",
        "book_url": _skyscanner_fallback_url(origin_iata, destination_iata, departure_date),
        "source": "booking_deeplink",
        "is_mock": True,
        "notes": note,
    }


async def _duffel_post(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST to Duffel; return parsed 'data' field. Raises on HTTP errors."""
    headers = {
        "Authorization": f"Bearer {_DUFFEL_TOKEN}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    resp = await client.post(f"{_DUFFEL_URL}{path}", json=body, headers=headers)
    resp.raise_for_status()
    return (resp.json() or {}).get("data", {}) or {}


async def _duffel_book_flight(
    origin_iata: str, destination_iata: str, departure_date: str
) -> Optional[dict[str, Any]]:
    """Call Duffel sandbox: offer request, then attempt order. Returns dict on
    success or None on failure (caller falls back to deep link)."""
    offer_req_body = {
        "data": {
            "slices": [{
                "origin": origin_iata,
                "destination": destination_iata,
                "departure_date": departure_date,
            }],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy",
        }
    }
    async with httpx.AsyncClient(timeout=_DUFFEL_TIMEOUT) as client:
        try:
            offer_data = await _duffel_post(client, "/air/offer_requests", offer_req_body)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Duffel offer_requests failed: %s", exc)
            return None

        offers = offer_data.get("offers") or []
        if not offers:
            logger.warning(
                "Duffel returned 0 offers for %s->%s %s",
                origin_iata, destination_iata, departure_date,
            )
            return None
        offer = offers[0]
        offer_id = offer.get("id", "")
        total_amount = offer.get("total_amount")
        total_currency = offer.get("total_currency", "SGD")
        owner_name = (offer.get("owner") or {}).get("name", "Duffel Airways")
        try:
            price: Optional[float] = float(total_amount) if total_amount is not None else None
        except (TypeError, ValueError):
            price = None

        order_body = {
            "data": {
                "selected_offers": [offer_id],
                "passengers": [{
                    "type": "adult", "title": "mr",
                    "given_name": "Demo", "family_name": "User",
                    "born_on": "1990-01-01", "gender": "m",
                    "email": "demo@tripcanvas.dev", "phone_number": "+6512345678",
                }],
                "payments": [{
                    "type": "balance",
                    "currency": total_currency,
                    "amount": str(total_amount) if total_amount is not None else "0",
                }],
            }
        }
        try:
            order_data = await _duffel_post(client, "/air/orders", order_body)
        except (httpx.HTTPError, ValueError) as exc:
            # Graceful degrade: keep offer-level confirmation (sandbox order
            # creation often fails on passenger schema; offer is enough for demo).
            logger.warning("Duffel orders failed (%s); using offer %s", exc, offer_id)
            return {
                "booking_id": offer_id,
                "category": "flight",
                "name": f"{owner_name} {origin_iata}->{destination_iata} ({departure_date})",
                "price_estimate_sgd": price,
                "status": "confirmed",
                "book_url": f"https://app.duffel.com/offers/{offer_id}",
                "source": "duffel_sandbox",
                "is_mock": True,
                "notes": f"Duffel sandbox offer {offer_id}; price {total_currency} {total_amount}.",
            }

        order_id = order_data.get("id") or offer_id
        booking_reference = order_data.get("booking_reference", "")
        return {
            "booking_id": order_id,
            "category": "flight",
            "name": f"{owner_name} {origin_iata}->{destination_iata} ({departure_date})",
            "price_estimate_sgd": price,
            "status": "confirmed",
            "book_url": f"https://app.duffel.com/orders/{order_id}",
            "source": "duffel_sandbox",
            "is_mock": True,
            "notes": (
                f"Duffel sandbox order {order_id} (ref {booking_reference}); "
                f"price {total_currency} {total_amount}."
            ),
        }


# ---------------------------------------------------------------------------
# Function tools
# ---------------------------------------------------------------------------


@function_tool
async def book_flight(
    origin_iata: str,
    destination_iata: str,
    departure_date: str,
    estimated_price_sgd: Optional[float] = None,
) -> dict:
    """Book a flight via Duffel sandbox; fall back to deep-link composer.

    origin_iata and destination_iata are 3-letter IATA codes (e.g. 'SIN', 'NRT').
    departure_date is YYYY-MM-DD. status='confirmed' only when Duffel sandbox
    responds; otherwise status='reserved' with a Skyscanner deep link.
    """
    if not _DUFFEL_ENABLED:
        return _flight_deeplink_dict(
            origin_iata, destination_iata, departure_date, estimated_price_sgd,
            "Duffel sandbox disabled (no DUFFEL_TEST_TOKEN); reserved via deep link only.",
        )
    try:
        result = await _duffel_book_flight(origin_iata, destination_iata, departure_date)
    except Exception as exc:  # noqa: BLE001 — tool must never raise
        logger.warning("Unexpected Duffel error: %s", exc)
        result = None
    if result is None:
        return _flight_deeplink_dict(
            origin_iata, destination_iata, departure_date, estimated_price_sgd,
            "Duffel sandbox unavailable; reserved via deep link only.",
        )
    if result.get("price_estimate_sgd") is None and estimated_price_sgd is not None:
        result["price_estimate_sgd"] = estimated_price_sgd
    return result


@function_tool
async def book_hotel(
    city: str,
    checkin: str,
    checkout: str,
    hotel_name: str,
    estimated_price_per_night_sgd: Optional[float] = None,
    guests: int = 2,
) -> dict:
    """Compose a Booking.com search URL for a hotel; return a reserved BookingItem.

    No external API call — pure URL composition. status='reserved'.
    """
    try:
        return {
            "booking_id": _mock_booking_id("hotel", city, checkin),
            "category": "hotel",
            "name": hotel_name,
            "price_estimate_sgd": estimated_price_per_night_sgd,
            "status": "reserved",
            "book_url": _booking_com_url(city, checkin, checkout, guests),
            "source": "booking_deeplink",
            "is_mock": True,
            "notes": (
                f"Reserved for {checkin}->{checkout} ({guests} adults). "
                "Click book_url to confirm on Booking.com."
            ),
        }
    except Exception as exc:  # noqa: BLE001 — tool must never raise
        logger.warning("book_hotel unexpected error: %s", exc)
        return {
            "booking_id": _mock_booking_id("hotel", city or "unknown", checkin or "unknown"),
            "category": "hotel",
            "name": hotel_name or "(unknown hotel)",
            "price_estimate_sgd": estimated_price_per_night_sgd,
            "status": "reserved",
            "book_url": "https://www.booking.com/",
            "source": "booking_deeplink",
            "is_mock": True,
            "notes": "Reserved via Booking.com (URL composition fallback).",
        }


@function_tool
async def book_attraction(
    name: str,
    city: str,
    estimated_price_sgd: Optional[float] = None,
) -> dict:
    """Compose a Klook search URL for an attraction; return a reserved BookingItem."""
    try:
        return {
            "booking_id": _mock_booking_id("attraction", name, city),
            "category": "attraction",
            "name": name,
            "price_estimate_sgd": estimated_price_sgd,
            "status": "reserved",
            "book_url": _klook_url(name),
            "source": "klook_deeplink",
            "is_mock": True,
            "notes": f"Reserved via Klook search for {name} in {city}.",
        }
    except Exception as exc:  # noqa: BLE001 — tool must never raise
        logger.warning("book_attraction unexpected error: %s", exc)
        return {
            "booking_id": _mock_booking_id("attraction", name or "unknown", city or "unknown"),
            "category": "attraction",
            "name": name or "(unknown attraction)",
            "price_estimate_sgd": estimated_price_sgd,
            "status": "reserved",
            "book_url": "https://www.klook.com/",
            "source": "klook_deeplink",
            "is_mock": True,
            "notes": "Reserved via Klook (URL composition fallback).",
        }


# ---------------------------------------------------------------------------
# Agent + runner
# ---------------------------------------------------------------------------


booking_agent = Agent(
    name="booking_agent",
    model="gpt-5.5-2026-04-23",
    tools=[book_flight, book_hotel, book_attraction],
    instructions=(
        "You are a booking agent. Given enricher output (a recommended hotel, recommended "
        "flight string, and list of attractions), call the appropriate tools to produce a "
        "BookingResult. For flights, convert city names to IATA codes using your knowledge "
        "(Singapore->SIN, Tokyo->NRT or HND, Osaka->KIX, etc.) before calling book_flight. "
        "Call book_hotel ONCE for the recommended hotel. Call book_attraction ONCE for each "
        "attraction. If no flight is recommended (empty string), skip book_flight entirely. "
        "After all tool calls, assemble the BookingResult: items is the list of returned "
        "BookingItems; total_estimate_sgd is the sum of non-null price_estimate_sgd values; "
        "is_mock is True. Do NOT fabricate booking_ids or URLs — only use what the tools return."
    ),
    output_type=BookingResult,
)


async def _run_agent_with_fallback(agent: Agent, prompt: str, max_turns: int) -> RunResult:
    """Run agent; fall back to gpt-4o clone on model-not-found errors."""
    try:
        return await Runner.run(agent, prompt, max_turns=max_turns)
    except _MODEL_ERRORS:
        logger.warning("Model unavailable for %s; falling back to gpt-4o", agent.name)
        return await Runner.run(agent.clone(model="gpt-4o"), prompt, max_turns=max_turns)


def _booking_prompt(
    destination_city: str,
    start_date: str,
    end_date: str,
    recommended_hotel: str,
    recommended_flight: str,
    origin_city: Optional[str],
    attractions: list[str],
) -> str:
    attractions_block = "\n".join(f"  - {a}" for a in attractions) if attractions else "  (none)"
    return (
        f"Destination: {destination_city}\n"
        f"Trip dates: {start_date} -> {end_date}\n"
        f"Origin city: {origin_city or '(none)'}\n"
        f"Recommended hotel: {recommended_hotel}\n"
        f"Recommended flight: {recommended_flight or '(none)'}\n"
        f"Attractions to reserve:\n{attractions_block}\n\n"
        "Call the appropriate booking tools and assemble a BookingResult."
    )


async def book_trip(
    destination_city: str,
    start_date: str,
    end_date: str,
    recommended_hotel: str,
    recommended_flight: str,
    origin_city: Optional[str],
    attractions: list[str],
    payment_provider: Optional[PaymentProvider] = None,
) -> BookingResult:
    """Run booking_agent under a 25s wall budget, then settle each booking via the
    PaymentProvider (AP2 + x402). Always returns — never raises.

    `payment_provider` defaults to MockSettlementProvider (no network). Zhi Hao
    passes a real AP2 + x402 provider to perform a genuine agentic payment; the
    booking items stay is_mock=True regardless.
    """
    provider = payment_provider or _default_payment_provider()
    prompt = _booking_prompt(
        destination_city, start_date, end_date,
        recommended_hotel, recommended_flight, origin_city, attractions,
    )
    try:
        run_result = await asyncio.wait_for(
            _run_agent_with_fallback(booking_agent, prompt, max_turns=20),
            timeout=_BOOKING_AGENT_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001 — never raise
        logger.warning("book_trip failed (%s); returning empty mock result", exc)
        return BookingResult(items=[], total_estimate_sgd=0.0, is_mock=True)

    final = run_result.final_output
    if not isinstance(final, BookingResult):
        logger.warning("booking_agent returned non-BookingResult: %s", type(final))
        return BookingResult(items=[], total_estimate_sgd=0.0, is_mock=True)

    # Hard-enforce fulfillment invariants regardless of model output:
    #   (1) is_mock=True on every item
    #   (2) status="confirmed" ONLY for the deprecated source="duffel_sandbox" — demote otherwise.
    sanitized: list[BookingItem] = []
    for item in final.items:
        updates: dict[str, Any] = {"is_mock": True}
        if item.status == "confirmed" and item.source != "duffel_sandbox":
            logger.warning(
                "Demoting status='confirmed' to 'reserved' for non-sandbox item %s (source=%s)",
                item.booking_id, item.source,
            )
            updates["status"] = "reserved"
        sanitized.append(item.model_copy(update=updates))

    # Agentic payment: settle each booking concurrently via the PaymentProvider.
    # Payment is SEPARATE from fulfillment — items stay is_mock=True; settlement
    # carries the (mock this round) AP2/x402 record.
    settlements = await asyncio.gather(*(_settle_item(provider, it) for it in sanitized))
    settled_items = [
        it.model_copy(update={"settlement": s}) for it, s in zip(sanitized, settlements)
    ]
    total_settled = sum(
        s.amount_sgd for s in settlements
        if s.payment_status in ("settled", "mock") and s.amount_sgd is not None
    )
    any_real = any(not s.is_mock_settlement for s in settlements)
    return BookingResult(
        items=settled_items,
        total_estimate_sgd=final.total_estimate_sgd,
        is_mock=True,
        payment_protocol="ap2_x402",
        total_settled_sgd=round(total_settled, 2),
        is_mock_settlement=not any_real,
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("=" * 65)
    print("spike_booking.py smoke test")
    print("=" * 65)
    result = asyncio.run(
        book_trip(
            destination_city="Tokyo",
            start_date="2026-06-10",
            end_date="2026-06-13",
            recommended_hotel="Grand Hyatt Tokyo",
            recommended_flight="Scoot TR828 SIN->NRT ~SGD 523",
            origin_city="Singapore",
            attractions=["Tokyo Dream Park", "Harry Potter Cafe", "Sando Lab Tokyo"],
        )
    )
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    for item in result.items:
        assert item.is_mock is True, f"is_mock must be True for {item.booking_id}"
        if item.status == "confirmed":
            assert item.source == "duffel_sandbox", (
                f"confirmed only with duffel_sandbox, got {item.source}"
            )
        assert item.settlement is not None, f"missing settlement for {item.booking_id}"
        if item.settlement.is_mock_settlement:
            assert item.settlement.payment_status != "settled", (
                f"mock settlement must not be 'settled' for {item.booking_id}"
            )
        assert item.settlement.payment_protocol == "ap2_x402"
    print(
        f"\n{len(result.items)} bookings, total ~SGD "
        f"{result.total_estimate_sgd:.2f}, mock={result.is_mock}; "
        f"payment={result.payment_protocol}, settled ~SGD {result.total_settled_sgd:.2f}, "
        f"mock_settlement={result.is_mock_settlement}"
    )
