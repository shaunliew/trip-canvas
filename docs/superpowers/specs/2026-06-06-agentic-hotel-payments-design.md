# Backend Agentic Hotel Payments Design

## Context

TripCanvas already has the agentic travel loop up to hotel-base optimization:

1. `/extract` turns Instagram Reel URLs into grounded places.
2. `/hotel-base` scores base areas and selects two hotel candidates.
3. `/itinerary` can accept the selected hotel-base result as planning context.

The next feature proves that TripCanvas can perform an agentic payment step after hotel selection. The goal for this run is backend proof, not frontend polish.

The payment demo is intentionally not a production hotel checkout. It should show an agent receiving user authority, attempting a paid booking action, satisfying a 402/x402-shaped payment requirement, and returning a demo-safe mock receipt.

## Decision

Implement a backend-first AP2-shaped mandate plus x402-shaped hotel booking flow.

The first implementation should use simulation-first x402 semantics with the same state machine as a real x402 integration:

1. The hotel booking agent requires payment before issuing a mock booking.
2. The first booking attempt yields payment instructions equivalent to `402 Payment Required`.
3. The TripCanvas orchestrator creates a payment proof bound to the booking attempt.
4. The orchestrator retries the booking with the payment proof.
5. The hotel booking agent returns a deterministic mock receipt.

If real x402 facilitator environment variables are present later, the payment adapter can be swapped behind the same service boundary.

## Scope

### In Scope

- Keep the current `/hotel-base` contract backward-compatible.
- Optimize `backend/data/hotel_base_output.json` so the selected hotel is booking-ready.
- Extend backend hotel-base models with optional typed booking fields.
- Add AP2-shaped mandate models for demo authorization.
- Add a hotel booking service that validates mandate constraints.
- Add an x402-shaped payment simulation adapter.
- Add a backend endpoint that proves the full payment loop.
- Add focused backend tests and a curl-verifiable smoke path.

### Out Of Scope

- Frontend audit trail implementation.
- Real production hotel reservation.
- Production card payment.
- Full AP2 compliance claim with signed mandate credentials.
- Full x402 facilitator/testnet dependency as the required demo path.
- ACP implementation.
- Changing the existing `/hotel-base` response shape in a breaking way.

## Existing Asset Reuse

`backend/data/hotel_base_output.json` becomes the hotel decision agent's authoritative tool output for this run. The file should remain valid as a `HotelBaseResult`, but the selected hotel candidate should include optional booking-ready metadata.

Recommended optional fields on each `HotelCandidate`:

```json
{
  "area": "Dotonbori",
  "price_per_night_sgd": 165,
  "station_walk_min": 6,
  "convenience_store_walk_min": 2,
  "quiet_score": 6,
  "route_efficiency_score": 9,
  "budget_tier": "mid_range",
  "amenities": ["breakfast", "near_station", "laundry"],
  "mock_available_rooms": 3,
  "room_type": "Standard double room",
  "cancellation_policy": "Free cancellation until 48 hours before check-in"
}
```

Recommended optional top-level payment context:

```json
{
  "payment_context": {
    "payment_protocol": "x402",
    "network": "base-sepolia",
    "asset": "USDC",
    "agent_payment_usd": "0.01",
    "mock_booking_only": true
  }
}
```

The backend should type these optional fields. Unknown untyped fields are not enough because Pydantic model loading may discard them before the booking service sees them.

## Backend API

### `POST /hotel-booking`

This endpoint proves the backend payment loop in one call. It is an orchestrator endpoint: callers may provide the selected hotel-base result and approved mandate, or they may use the backend smoke path that loads `hotel_base_output.json` and builds a default demo mandate. The backend then validates the mandate, performs the x402-shaped booking flow, and returns an audit trail plus receipt.

Request shape:

```json
{
  "trip_id": "tc-demo-osaka-001",
  "hotel_base": {},
  "mandate": {
    "mandate_id": "ap2-demo-tc-osaka-001",
    "mode": "autonomous",
    "allowed_action": "mock_hotel_booking",
    "city": "Osaka",
    "checkin": "2026-06-10",
    "checkout": "2026-06-13",
    "guests": 2,
    "budget": "mid_range",
    "hotel_preferences": ["near_station", "quiet", "near_convenience_store"],
    "max_total_sgd": 650,
    "max_agent_payment_usd": "0.01",
    "payment_protocol": "x402",
    "network": "base-sepolia",
    "expires_at": "2026-06-10T00:00:00Z",
    "requires_user_visible_receipt": true,
    "mock_booking_only": true
  },
  "idempotency_key": "tc-demo-osaka-001:ap2-demo-tc-osaka-001:hotel_forza_osaka_namba_dotonbori"
}
```

`hotel_base` and `mandate` may be omitted for the backend smoke path. In that case, the endpoint loads `backend/data/hotel_base_output.json` and builds a default unsigned demo mandate from the selected hotel, dates, and payment context.

Response shape:

```json
{
  "status": "mock_confirmed",
  "audit_events": [
    {
      "type": "mandate_validated",
      "message": "Mandate allows mock hotel booking within SGD 650."
    },
    {
      "type": "payment_required",
      "message": "Hotel booking agent requires 0.01 testnet USDC."
    },
    {
      "type": "payment_completed",
      "message": "x402 payment simulation completed.",
      "simulated": true
    },
    {
      "type": "booking_confirmed",
      "message": "Mock hotel booking receipt issued."
    }
  ],
  "payment": {
    "protocol": "x402",
    "network": "base-sepolia",
    "asset": "USDC",
    "amount": "0.01",
    "payer": "0xOrchestrator...",
    "payee": "0xHotelAgent...",
    "tx_hash": "0xSIMULATED...",
    "status": "simulated"
  },
  "receipt": {
    "type": "hotel_booking_receipt",
    "booking_id": "TC-MOCK-HOTEL-8F3A2C",
    "status": "mock_confirmed",
    "is_mock": true,
    "receipt_note": "Demo-safe mock booking. No real hotel reservation was created."
  }
}
```

## Service Boundaries

### Mandate Service

Responsibilities:

- Build or validate `BookingMandate`.
- Enforce `allowed_action == "mock_hotel_booking"`.
- Enforce `mock_booking_only == true`.
- Enforce mandate expiry.
- Enforce city, date, guest, and budget constraints that can be checked from fixture data.
- Return explicit failure reasons instead of partially booking.

### Hotel Booking Agent Service

Responsibilities:

- Load or receive a `HotelBaseResult`.
- Resolve `selected_hotel_id`.
- Validate selected hotel booking metadata.
- Calculate stay nights and estimated total SGD.
- Refuse if no rooms are available.
- Refuse if `estimated_total_sgd > mandate.max_total_sgd`.
- Issue deterministic `TC-MOCK-HOTEL-...` receipt only after valid payment proof.

### x402 Payment Adapter

Responsibilities:

- Produce payment instructions when the booking agent requires payment.
- Create an x402-shaped payment proof bound to:
  - `trip_id`
  - `mandate_id`
  - `hotel_id`
  - amount
  - network
  - idempotency key
- Return simulated tx metadata by default.
- Keep private keys and payment signatures server-side.

The adapter should be isolated so a real x402 facilitator implementation can replace the simulation later.

## Validation Rules

The backend must fail closed when:

- `HOTEL_BOOKING_MODE` is set and is not `mock`.
- `mandate.mock_booking_only` is not true.
- The mandate action is not `mock_hotel_booking`.
- The selected hotel cannot be found.
- The selected hotel lacks `price_per_night_sgd`.
- The calculated stay has zero or negative nights.
- The selected hotel has no mock rooms available.
- The estimated stay total exceeds `max_total_sgd`.
- The agent payment exceeds `max_agent_payment_usd`.
- Payment proof is absent when the seller requires payment.

Failure responses should identify the violated constraint and should not include a mock receipt.

## Determinism And Idempotency

The booking ID should be deterministic:

```text
TC-MOCK-HOTEL-{sha1(trip_id|mandate_id|hotel_id|checkin|checkout|guests)[:8].upper()}
```

The payment simulation tx hash should also be deterministic from the idempotency key and payment request fields. Retrying the same request with the same idempotency key should return the same receipt and tx hash.

## Environment

Suggested backend environment variables:

```bash
X402_ENABLED=true
X402_MODE=simulation
X402_NETWORK=base-sepolia
X402_HOTEL_BOOKING_PRICE_USD=0.01
ORCHESTRATOR_WALLET_ADDRESS=0xOrchestratorDemo
HOTEL_AGENT_PAY_TO=0xHotelAgentDemo
HOTEL_BOOKING_MODE=mock
AP2_MANDATE_MODE=demo_unsigned
```

For V1, missing wallet addresses may fall back to obvious demo addresses only when `X402_MODE=simulation`. Private keys are not required for simulation and must not be exposed to the frontend or logs.

## Testing

Focused backend tests:

- `hotel_base_output.json` validates with optional booking fields.
- Selected hotel can be resolved and has booking-ready metadata.
- Mandate validation accepts the approved demo shape.
- Mandate validation rejects over-budget, wrong action, expired, and non-mock requests.
- Booking service returns payment required before proof.
- Orchestrator pays and retries, then receives a mock receipt.
- Idempotency returns stable booking ID and tx hash.
- Payment failure returns an audit event and no receipt.

Smoke proof:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments -v
uv run uvicorn backend.main:app --port 8000
curl -X POST http://localhost:8000/hotel-booking \
  -H "Content-Type: application/json" \
  -d '{"trip_id":"tc-demo-osaka-001","idempotency_key":"tc-demo-osaka-001:demo"}'
```

The curl response should include `payment.status = "simulated"`, a `payment_required` audit event, a `payment_completed` audit event, and a `receipt.booking_id` beginning with `TC-MOCK-HOTEL-`.

## Acceptance Criteria

- A backend-only test proves the AP2-shaped mandate plus x402-shaped payment loop.
- The selected hotel comes from `backend/data/hotel_base_output.json`.
- The booking action is payment-gated; hotel recommendation remains free.
- The backend returns a visible audit trail from mandate validation to mock receipt.
- The receipt clearly says no real hotel reservation was created.
- Constraint violations do not return receipts.
- The current `/hotel-base` and `/itinerary` contracts remain backward-compatible.

## Risks And Tradeoffs

- Simulation-first x402 improves demo reliability but does not prove chain settlement. Mitigation: keep the adapter boundary and response fields aligned with real x402 so facilitator integration can be added later.
- Adding optional booking fields keeps the current flow stable but requires careful typing so fields survive Pydantic validation.
- A single `/hotel-booking` orchestrator endpoint is simpler for backend proof, but the frontend may later want more granular streaming audit events. That should be added after the backend proof is stable.
