# Agentic Payments For TripCanvas

> Current reference as of 2026-06-07. The implementation lives in `backend/payments/`, with compatibility exports through `backend/spike_agentic_payments.py`. The itinerary booking overlay still has the older `PaymentProvider` seam in `backend/spike_booking.py`, but the explicit hotel-booking endpoint flow is `POST /ap2/hotel-booking-mandate` then `POST /hotel-booking`.

## Decision

TripCanvas will use **AP2-inspired authorization** plus **x402 machine payment** for the hotel booking demo.

The product story is:

1. The user gives TripCanvas permission to book a mock hotel within visible constraints.
2. The orchestrator agent chooses a hotel using Reel-extracted places, route efficiency, weather-aware itinerary needs, and user hotel preferences.
3. The hotel booking agent requires payment before issuing the booking.
4. The orchestrator pays the hotel booking agent through x402 on a testnet or sandbox network.
5. The hotel booking agent returns a mock hotel reservation receipt.
6. The existing itinerary remains grounded on the selected hotel base, and the UI shows the AP2/x402 booking receipt after user approval.

This is intentionally not a production hotel checkout. The goal is to show an end-to-end AI-native flow where agents can reason, request authority, pay another agent, and return a booking artifact.

## Protocol Roles

| Layer | What It Proves | TripCanvas Usage |
| --- | --- | --- |
| AP2 | The user authorized the agent to make a purchase under constraints | Use an AP2-shaped mandate that captures city, dates, guests, max spend, hotel preferences, and mock-booking-only scope |
| x402 | One machine can pay another over HTTP | The orchestrator wallet pays the hotel agent wallet before `/book` returns a mock booking |
| TripCanvas | Travel reasoning and demo-safe booking | Extract places from Reels, score hotel bases, show a visible agent audit trail, and return `TC-MOCK-...` booking IDs |

ACP is not in scope for this version. ACP is more relevant when TripCanvas needs a full merchant checkout protocol with catalog, cart, payment credential relay, order lifecycle, refunds, and fulfillment webhooks. For this demo, AP2 plus x402 is narrower and better aligned with agent-to-agent payment.

## Goals

- Show that TripCanvas is an agentic travel product, not just a map UI.
- Show the user explicitly authorizing autonomous hotel booking constraints.
- Show a visible agent audit trail: mandate, hotel reasoning, x402 payment, mock booking, itinerary update.
- Use real x402 mechanics where practical: `402 Payment Required`, payment instructions, orchestrator payment, retry with payment proof, booking response.
- Keep hotel booking demo-safe with no real hotel reservation, no production card charge, and no real guest PII.
- Keep the existing Mapbox-first TripCanvas flow intact.

## Non-Goals

- No real production hotel booking.
- No production card payment.
- No ACP implementation.
- No full AP2 compliance claim. TripCanvas signs and verifies demo mandates, but this is still AP2-style demo signing rather than a production AP2 credential-provider integration.
- No hidden chain-of-thought display. The UI shows user-facing rationale, scores, evidence, and tool/status events.
- No dependency on a live hotel supplier API for the demo path.

## Actors

### User

Sets travel dates, Reel URLs, hotel preferences, and booking constraints. The user must approve the booking mandate before the orchestrator can pay.

### TripCanvas Orchestrator Agent

Owns the trip run. It extracts places, asks the hotel-base optimizer for candidates, plans the itinerary from the selected hotel base, creates the AP2-shaped booking mandate after user approval, pays the hotel booking agent through x402, and returns the mock receipt to the UI.

### Hotel Decision Agent

Compares hotel candidates against user preferences and trip geometry. It produces the decision trace:

- Interpreted hotel preferences.
- Extracted place cluster.
- Candidate hotel scores.
- Route efficiency.
- Station access.
- Quietness.
- Convenience-store access.
- Budget fit.
- Tradeoffs.
- Final selected hotel.

### Hotel Booking Agent

Acts as the paid seller/service. It exposes a booking endpoint that is x402-gated. After valid payment, it returns a mock booking receipt.

### x402 Facilitator

Verifies and settles the x402 payment payload so the hotel booking agent does not need to implement all chain verification logic itself.

### Trusted Surface

The TripCanvas UI surface where the user reviews and approves the mandate. In V1 this can be an explicit confirmation panel. In a stricter AP2 implementation, this would produce signed mandate credentials.

## Wallets And Environment

Prepare two wallets:

1. **Orchestrator wallet**
   - Buyer wallet.
   - Held by TripCanvas backend only.
   - Pays the hotel booking agent through x402.

2. **Hotel agent wallet**
   - Seller wallet.
   - Used as the x402 `payTo` address.
   - Receives the testnet or sandbox payment.

Suggested environment variables:

```bash
X402_MODE=real
X402_NETWORK=eip155:84532
X402_FACILITATOR_URL=https://x402.org/facilitator
X402_HOTEL_BOOKING_PRICE_USD=0.01

ORCHESTRATOR_WALLET_ADDRESS=0x...
ORCHESTRATOR_PRIVATE_KEY=...
HOTEL_AGENT_PAY_TO=0x...

HOTEL_BOOKING_MODE=mock
AP2_MODE=disabled
AP2_DEMO_ISSUER=tripcanvas-demo-trusted-surface
AP2_DEMO_AUDIENCE=tripcanvas-hotel-booking-agent
AP2_MANDATE_TTL_SECONDS=180
AP2_DEMO_SIGNING_SECRET=...
```

Guardrails:

- Never commit wallet private keys.
- Never expose private keys to the frontend.
- Do not log private keys, raw payment signatures, or full authorization headers.
- Use tiny testnet/sandbox amounts only.
- Fail closed if `HOTEL_BOOKING_MODE` is not `mock`.
- Fail closed in `X402_MODE=real`; do not fall back to simulated payment if signing, verification, or settlement fails.
- Keep `AP2_MODE=disabled` as the default local path. Set `AP2_MODE=demo_signed`
  only when the backend should require a signed AP2 demo mandate before x402.
- `AP2_DEMO_SIGNING_SECRET` is required only in `AP2_MODE=demo_signed`.

## Data Fixtures

Because the demo does not call a real hotel supplier API, the hotel booking agent needs committed fixture data.

For the current backend proof path, the hotel booking agent uses
`backend/data/planner_output.json` as its tool payload. The selected
`hotel_options` entry (`is_best: true`) should carry the mock-booking metadata
needed for payment validation and receipt generation.

### Hotel Inventory Fixture

Suggested path:

```text
backend/data/hotel_inventory.json
```

Example shape:

```json
{
  "hotels": [
    {
      "id": "hotel_forza_osaka_namba",
      "name": "Hotel Forza Osaka Namba Dotonbori",
      "city": "Osaka",
      "area": "Dotonbori",
      "lat": 34.6687,
      "lng": 135.5032,
      "price_per_night_sgd": 165,
      "station_walk_min": 5,
      "convenience_store_walk_min": 2,
      "quiet_score": 6,
      "route_efficiency_score": 9,
      "budget_tier": "mid_range",
      "amenities": ["laundry", "breakfast", "near_station"],
      "mock_available_rooms": 3,
      "booking_url": "https://www.hotelforza.jp/osakanamba/en/"
    }
  ]
}
```

### AP2 Demo Signed Booking Mandate

This is the user-authorized purchase scope. In backend AP2 demo signed mode,
`POST /ap2/hotel-booking-mandate` signs the final hotel checkout terms and
`POST /hotel-booking` verifies that signed mandate before creating any x402
payment proof.

```json
{
  "mandate_id": "ap2-demo-tc-osaka-001",
  "trip_id": "tc-demo-osaka-001",
  "mode": "autonomous",
  "allowed_action": "mock_hotel_booking",
  "city": "Osaka",
  "checkin": "2026-06-10",
  "checkout": "2026-06-13",
  "guests": 2,
  "budget": "mid_range",
  "hotel_preferences": ["near_station", "quiet", "near_convenience_store"],
  "max_total_sgd": 650,
  "max_agent_payment_usd": 0.01,
  "payment_protocol": "x402",
  "network": "eip155:84532",
  "expires_at": "2026-06-10T00:00:00Z",
  "requires_user_visible_receipt": true,
  "mock_booking_only": true
}
```

The signed mandate binds the selected hotel, stay, idempotency key, payment
amount, payer, payee, network, and x402 payment request id. The default TTL is
180 seconds via `AP2_MANDATE_TTL_SECONDS`; expired or tampered mandates are
rejected before any x402 adapter call.

This is AP2-style demo signing for the hackathon backend flow, not production
AP2 compliance. Production AP2 would require a real credential provider,
production trust model, and full protocol conformance beyond this HMAC-signed
demo mandate.

## Backend Flow

The current frontend runs booking after itinerary generation, once the user can inspect and approve the selected hotel.

```text
POST /extract
  -> extracted real places

POST /hotel-base
  -> free hotel decision trace and selected hotel candidate

POST /itinerary
  -> itinerary uses selected hotel base

User approves AP2-shaped mandate
  -> POST /ap2/hotel-booking-mandate signs the final hotel checkout terms

POST /hotel-booking
  -> orchestrator calls hotel booking agent
  -> hotel booking agent returns 402 Payment Required
  -> orchestrator pays with x402
  -> orchestrator retries with payment proof
  -> hotel booking agent returns mock booking receipt
```

The `/hotel-base` step should remain free. The x402 gate should protect only the booking action, not the decision preview. This lets the user see why the hotel is being chosen before any agent payment happens.

## Booking Response Contract

The mock booking receipt should be explicit that it is not a real hotel reservation.

```json
{
  "type": "hotel_booking_receipt",
  "booking_id": "TC-MOCK-HOTEL-8F3A2C",
  "status": "mock_confirmed",
  "is_mock": true,
  "hotel": {
    "id": "hotel_forza_osaka_namba",
    "name": "Hotel Forza Osaka Namba Dotonbori",
    "area": "Dotonbori",
    "city": "Osaka",
    "lat": 34.6687,
    "lng": 135.5032
  },
  "stay": {
    "checkin": "2026-06-10",
    "checkout": "2026-06-13",
    "nights": 3,
    "guests": 2
  },
  "pricing": {
    "price_per_night_sgd": 165,
    "estimated_total_sgd": 495,
    "agent_payment_usd": "0.01"
  },
  "payment": {
    "protocol": "x402",
    "network": "eip155:84532",
    "payer": "0xOrchestrator...",
    "payee": "0xHotelAgent...",
    "amount": "0.01",
    "asset": "USDC",
    "tx_hash": "0x..."
  },
  "mandate": {
    "mandate_id": "ap2-demo-tc-osaka-001",
    "allowed_action": "mock_hotel_booking",
    "mock_booking_only": true
  },
  "receipt_note": "Demo-safe mock booking. No real hotel reservation was created."
}
```

## Agent Audit Trail UI

Use the right-side agent panel as the main surface. Keep the map primary and make details expandable.

Recommended timeline:

1. **Mandate prepared**
   - "User authorized a mock hotel booking within SGD 650, near station, quiet, convenience nearby."

2. **Hotel candidates scored**
   - Show the selected hotel and one alternate.
   - Show score categories instead of hidden chain-of-thought.

3. **Booking agent requested payment**
   - "Hotel booking agent requires 0.01 testnet USDC for mock booking capability."

4. **x402 payment completed**
   - Show network, payer, payee, amount, and tx hash if available.

5. **Mock booking confirmed**
   - Show `TC-MOCK-...`, hotel, dates, guests, and mock-only disclaimer.

6. **Receipt ready**
   - "The itinerary remains routed from the selected hotel base; the hotel receipt is demo-safe and mock-only."

## User-Facing Hotel Reasoning

Expose a decision trace, not raw model thinking.

Good:

- "Matched user preference: near station."
- "5 minute walk to nearest major station."
- "Central to 8 of 11 extracted places."
- "Lower quiet score than Umeda, but better route efficiency for Dotonbori and Namba places."
- "Estimated total SGD 495 is under the SGD 650 mandate."

Avoid:

- Hidden chain-of-thought.
- Long internal deliberation.
- Claims that cannot be traced to fixture data, map geometry, or source URLs.
- Saying a real booking was created.

## Failure Modes

| Failure | Expected Behavior |
| --- | --- |
| User does not approve mandate | Do not call the x402 booking step. Continue with hotel recommendation only. |
| x402 simulation mode | Return a mock booking with `payment.status = "simulated"` and a simulated tx hash. |
| x402 real mode is misconfigured | Return `payment_failed` with no receipt. Do not fall back to simulation. |
| x402 payment fails | Show failed payment in audit trail, keep selected hotel, and continue itinerary without booking receipt. |
| Hotel inventory has no matching room | Show no booking created and fall back to itinerary planning from selected base area. |
| Mandate constraints are violated | Refuse booking and show which constraint failed. |
| Network/facilitator timeout | Show payment unavailable and allow retry. Do not silently mark booking confirmed. |

## Security And Reliability Guardrails

- Use idempotency keys for booking attempts so refresh/retry does not create multiple mock receipts.
- Bind payment attempts to `trip_id`, `mandate_id`, `hotel_id`, and booking amount.
- Expire mandates quickly.
- Enforce `max_agent_payment_usd` before payment.
- Enforce `max_total_sgd` before booking.
- Require `mock_booking_only = true` in V1.
- Keep all signing/payment logic server-side.
- Redact secrets and payment signatures from logs.
- Prefer deterministic fixture fallback for demo reliability.

## Suggested Implementation Slices

1. **Contracts and fixtures**
   - Add AP2-shaped mandate models.
   - Add hotel inventory fixture.
   - Add booking receipt schema.

2. **Hotel booking agent**
   - Add mock hotel booking service that validates mandate constraints.
   - Return deterministic `TC-MOCK-HOTEL-...` IDs.

3. **x402 integration**
   - Add real x402 settlement behind the hotel booking payment adapter.
   - Add orchestrator buyer behavior to sign, verify, settle, and retry.
   - Keep simulation fallback explicitly labeled and unavailable in `X402_MODE=real`.

4. **Orchestrator/UI events**
   - Show mandate, payment, and receipt events in the frontend booking flow after the itinerary is visible.

5. **Frontend audit trail**
   - Add the AP2/x402 booking timeline to the agent panel.
   - Keep details collapsed by default.
   - Show mock-only and testnet labels clearly.

6. **Verification**
   - Unit test mandate constraint validation.
   - Unit test deterministic mock booking IDs.
   - Smoke test payment-required and paid booking flows.
   - Typecheck frontend contracts.
   - Manually run the demo path on localhost.

## Demo Success Criteria

- The user can approve a visible hotel-booking mandate.
- The hotel decision trace clearly explains why the selected hotel matches the trip.
- The booking action requires payment, not the free recommendation step.
- The orchestrator pays the hotel agent wallet through x402 or a clearly labeled x402 simulation.
- The UI shows an audit trail from mandate to payment to mock booking receipt.
- The final itinerary uses the selected hotel base as the route hub, and the approved booking receipt matches that selected hotel.
- The demo never implies a real hotel reservation was created.

## References

- AP2 specification: https://ap2-protocol.org/ap2/specification/
- Google AP2 announcement: https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol/
- x402 documentation: https://docs.x402.org/
- x402 seller quickstart: https://docs.x402.org/getting-started/quickstart-for-sellers
- OpenAI ACP announcement for contrast only: https://openai.com/index/buy-it-in-chatgpt/
