# AP2 Backend Demo Mandate Design

## Context

TripCanvas already has a backend hotel booking payment proof path:

1. `POST /hotel-booking` normalizes a selected hotel and AP2-shaped `BookingMandate`.
2. The hotel booking service returns x402-style payment instructions.
3. The orchestrator creates a payment proof through either simulation mode or the real x402 adapter.
4. The backend returns a deterministic mock hotel receipt.

The missing backend feature is a signed human-confirmation layer before x402. For this sprint, the goal is demo-grade AP2-style authorization, not production AP2 compliance.

## Decision

Add a backend HMAC-signed AP2 demo mandate layer before the existing `/hotel-booking` x402 settlement path.

`AP2_MODE=disabled` stays the default so current local smoke behavior remains unchanged. When `AP2_MODE=demo_signed`, `/hotel-booking` must verify a signed AP2 demo mandate before it creates any x402 payment proof.

The booking remains mock-only. AP2 proves that the user confirmed a specific mock hotel checkout. x402 remains the payment/settlement layer.

## Goals

- Prove a human-present confirmation step for the selected hotel booking terms.
- Bind the signed mandate to the selected hotel, stay, idempotency key, payment amount, payer, payee, network, and x402 payment request id.
- Reject missing, expired, tampered, or mismatched mandates before any x402 adapter call.
- Keep the current `/hotel-booking` response backward-compatible in default mode.
- Keep implementation and tests backend-only for this sprint.

## Non-Goals

- No production AP2 credential provider.
- No browser WebCrypto signing.
- No frontend hotel payment panel in this sprint.
- No real hotel fulfillment.
- No claim that TripCanvas is production AP2 compliant.
- No replacement of x402. AP2 is layered above x402 as authorization proof.

## API Design

### `POST /ap2/hotel-booking-mandate`

Creates a signed AP2 demo mandate for the exact final hotel checkout/payment terms. It does not run x402 and does not create a booking.

Request shape:

```json
{
  "trip_id": "tc-demo-osaka-001",
  "hotel_base": {},
  "mandate": {},
  "idempotency_key": "tc-demo-osaka-001:ap2-demo-tc-osaka-001:hotel_royal_park_shiodome",
  "user_confirmation": {
    "confirmed": true,
    "button_label": "Confirm Hotel Booking",
    "trusted_surface": "tripcanvas-web"
  }
}
```

Response shape:

```json
{
  "status": "signed",
  "ap2": {
    "status": "created",
    "mode": "direct",
    "mandate_id": "ap2-demo-tc-osaka-001",
    "checkout_hash": "sha256:...",
    "confirmation_id": "ap2_confirm_...",
    "confirmed_at": "2026-06-06T04:45:00Z",
    "issuer": "tripcanvas-demo-trusted-surface",
    "signed_mandate": {}
  },
  "preview": {
    "hotel": {},
    "stay": {},
    "pricing": {},
    "payment": {}
  },
  "error": null
}
```

If the user confirmation is missing or false, return `status="rejected"` with `error.code="ap2_confirmation_required"`.

### `POST /hotel-booking`

Extend the existing request with:

```json
{
  "ap2_signed_mandate": {}
}
```

Default behavior remains unchanged when `AP2_MODE=disabled`. When `AP2_MODE=demo_signed`, the backend verifies `ap2_signed_mandate` before creating a payment proof. AP2 failure returns `status="rejected"` and no receipt.

Add optional AP2 summaries to the existing response and receipt:

```json
{
  "ap2": {
    "status": "verified",
    "mode": "direct",
    "mandate_id": "ap2-demo-tc-osaka-001",
    "checkout_hash": "sha256:...",
    "confirmation_id": "ap2_confirm_...",
    "confirmed_at": "2026-06-06T04:45:00Z",
    "issuer": "tripcanvas-demo-trusted-surface"
  }
}
```

## Signed Mandate Format

Use a compact JWS-like shape:

```json
{
  "format": "tripcanvas-ap2-demo-jws",
  "protected": "base64url-json-header",
  "payload": "base64url-json-payload",
  "signature": "base64url-hmac-sha256",
  "payload_json": {}
}
```

Header:

```json
{
  "alg": "HS256",
  "typ": "JWT",
  "kid": "tripcanvas-demo-ap2-v1"
}
```

Payload fields:

- `vct="tripcanvas.ap2.hotel_booking.confirmation.1"`
- `mode="direct"`
- `issuer`
- `audience`
- `mandate_id`
- `trip_id`
- `idempotency_key`
- `checkout`
- `payment`
- `constraints`
- `confirmation`
- `iat`
- `exp`
- `nonce`

The backend may return `payload_json` for demo readability, but verification must decode and verify the encoded `protected.payload.signature` values. It must not trust `payload_json`.

Use canonical JSON with `sort_keys=True`, compact separators, and `default=str`. Use URL-safe base64 without padding. Sign with HMAC-SHA256.

## TTL And Environment

Default AP2 environment:

```bash
AP2_MODE=disabled
AP2_DEMO_ISSUER=tripcanvas-demo-trusted-surface
AP2_DEMO_AUDIENCE=tripcanvas-hotel-booking-agent
AP2_MANDATE_TTL_SECONDS=180
```

`AP2_DEMO_SIGNING_SECRET` is required only when `AP2_MODE=demo_signed`.

Mandate creation sets:

```text
exp = iat + AP2_MANDATE_TTL_SECONDS
```

The default signed mandate TTL is 180 seconds. Verification allows a 60-second future-`iat` clock skew and rejects later values with `ap2_mandate_not_yet_valid`.

## Verification Rules

When `AP2_MODE=demo_signed`, reject before x402 if any condition fails:

- signed mandate is missing
- signing secret is missing
- `format`, `alg`, `typ`, `kid`, or `vct` is unsupported
- HMAC signature is invalid
- `exp` is expired
- `iat` is more than 60 seconds in the future
- `trip_id` mismatches the normalized booking request
- `mandate_id` mismatches the normalized mandate
- `idempotency_key` mismatches the normalized booking request
- selected `hotel_id` mismatches the normalized selected hotel
- checkout hash does not match the canonical checkout object
- `constraints.allowed_action` is not `mock_hotel_booking`
- `checkout.mock_booking_only` is not true
- payment protocol, network, asset, amount, payer, payee, or payment request id mismatches the generated x402 payment instructions
- `confirmation.button_label` is not exactly `Confirm Hotel Booking`

Stable AP2 error codes:

```text
ap2_mandate_required
ap2_config_missing
ap2_mandate_malformed
ap2_signature_invalid
ap2_mandate_expired
ap2_mandate_not_yet_valid
ap2_mandate_trip_mismatch
ap2_mandate_checkout_mismatch
ap2_mandate_payment_mismatch
ap2_confirmation_required
```

AP2 rejection must not call `create_payment_proof`, must not call real x402, must not emit `payment_completed`, and must not return a receipt.

## Service Boundaries

### AP2 Demo Mandate Service

Responsibilities:

- Normalize the same request shape used by `/hotel-booking`.
- Resolve the selected hotel.
- Build the checkout preview.
- Build the x402 payment instructions that the mandate must bind to.
- Require explicit `AP2UserConfirmation`.
- Sign and return an AP2 demo mandate.
- Verify a signed mandate against normalized booking context and payment instructions.

### Existing Hotel Payment Service

Responsibilities:

- Keep existing mandate and hotel constraints.
- Keep current x402 simulation and real adapter behavior.
- Enforce AP2 verification only when `AP2_MODE=demo_signed`.
- Attach verified AP2 summary to successful responses and receipts.

## File Changes

Backend:

- `backend/spike_agentic_payments.py`
  - Add AP2 Pydantic models.
  - Add HMAC signing and verification helpers.
  - Add mandate creation function.
  - Extend `HotelBookingRequest` with optional `ap2_signed_mandate`.
  - Extend `HotelBookingResponse` and `HotelBookingReceipt` with optional AP2 summary.
  - Enforce AP2 verification in `run_payment_loop` before x402 proof creation.

- `backend/main.py`
  - Register `POST /ap2/hotel-booking-mandate`.

- `backend/tests/test_agentic_hotel_payments.py`
  - Add AP2 signing, verification, and fail-closed tests.

- `AGENTICPAYMENTS.md`
  - Document demo AP2 env vars and non-compliance caveat.
  - Document the 180-second mandate TTL.

## Testing Strategy

Focused tests:

- mandate creation rejects missing user confirmation
- mandate creation returns signed bundle and preview
- valid signed mandate allows x402 simulation
- `AP2_MODE=demo_signed` rejects missing mandate before x402
- tampered encoded payload rejects before x402
- expired mandate rejects before x402
- future-`iat` beyond 60 seconds rejects before x402
- hotel mismatch rejects before x402
- payment amount/network/payee/payment request mismatch rejects before x402
- AP2 failure does not call the payment adapter
- `AP2_MODE=disabled` preserves existing `/hotel-booking` smoke behavior

Validation commands:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments -v
uv run python -m unittest discover -s backend/tests -v
git diff --check
```

## Rollout

1. Ship AP2 backend code with `AP2_MODE=disabled` as the default.
2. Run existing backend tests to confirm compatibility.
3. Enable `AP2_MODE=demo_signed` in local demo env with `AP2_DEMO_SIGNING_SECRET`.
4. Smoke `POST /ap2/hotel-booking-mandate`.
5. Smoke `POST /hotel-booking` with the returned signed mandate in x402 simulation mode.
6. Only run real x402 after explicit approval because successful real mode can spend testnet USDC.

## Rollback

Set:

```bash
AP2_MODE=disabled
```

This returns `/hotel-booking` to the current behavior while leaving x402 intact.

## Acceptance Criteria

- Existing `/hotel-booking` behavior works unchanged when `AP2_MODE=disabled`.
- `POST /ap2/hotel-booking-mandate` returns a signed mandate and preview after explicit confirmation.
- `AP2_MODE=demo_signed` rejects missing, expired, tampered, or mismatched mandates before x402.
- Valid signed mandate allows the existing x402 simulation path and returns a mock hotel receipt.
- Successful response exposes AP2 verified status separately from x402 payment status.
- Docs clearly state this is AP2-style demo signing, not production AP2 compliance.
