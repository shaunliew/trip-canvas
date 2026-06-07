# AP2 Human In The Loop Implementation Plan

> Status: historical implementation plan. The AP2 demo mandate flow is now implemented in `backend/payments/` with compatibility exports through `backend/spike_agentic_payments.py`, and the frontend booking UI exists in `frontend/components/trip/BookingFlowPanel.tsx` plus `frontend/lib/trip/hotel-booking.ts`. Treat the task steps below as execution history, not current repo state.

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven development or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal demo-grade AP2 signed human confirmation layer before the existing `/hotel-booking` x402 settlement path.

**Architecture:** TripCanvas will keep x402 as the money movement layer and add AP2 as the user-authorization proof layer. The user will explicitly confirm the final hotel booking terms in the frontend; the backend will create and later verify a signed AP2 demo mandate bundle before allowing x402 settlement. This is intentionally a demo implementation, not a production AP2 credential-provider or payment-network integration.

**Tech Stack:** FastAPI, Pydantic, Python standard-library HMAC/SHA-256 for demo mandate signatures, existing x402 Python SDK path, Next.js App Router, React 19, TypeScript.

---

## Original Current State At Plan Time

The backend already proves the x402 half of the story:

- `backend/spike_agentic_payments.py` has `BookingMandate`, `PaymentInstructions`, `PaymentProof`, `PaymentReceipt`, `HotelBookingReceipt`, `AgenticHotelPaymentService`, `X402SimulationAdapter`, and `X402RealAdapter`.
- `POST /hotel-booking` is registered in `backend/main.py`.
- `X402_MODE=simulation` remains the default offline test path.
- `X402_MODE=real` performs real Base Sepolia x402 settlement and returns `payment.status="settled"`.
- `backend/data/planner_output.json` is the hotel booking tool payload for the selected hotel.
- At the time this plan was written, the frontend had no AP2/hotel-booking UI. The current repo now has that UI in `frontend/components/trip/BookingFlowPanel.tsx` and payment helpers in `frontend/lib/trip/hotel-booking.ts`.

The missing piece is AP2-style cryptographic authorization:

- The current `BookingMandate` is AP2-shaped, but it is not signed.
- There is no explicit final "Confirm hotel booking" gate in the frontend.
- `/hotel-booking` does not reject a request merely because the human confirmation signature is absent.

## AP2 Interpretation For This Demo

AP2 is the authorization layer. It answers: "What did the human authorize the agent to do?"

x402 is the settlement layer. It answers: "Did value move for this HTTP-gated action?"

TripCanvas should show both:

```text
Human confirms final hotel terms
  -> AP2 demo mandate is signed
  -> Backend verifies mandate signature and bound fields
  -> x402 pays hotel booking agent
  -> Mock hotel receipt is issued
```

Use AP2's human-present/direct idea for the minimal sprint:

- The user is present.
- The selected hotel and payment terms are known.
- The user directly confirms the closed checkout/payment terms.
- The backend verifies a signed mandate bundle before payment.

Do not implement the full AP2 production stack:

- No real Credential Provider.
- No real AP2 network verification.
- No external user credential enrollment.
- No production card/payment instrument credential.
- No claim of full AP2 compliance.

The UI copy must say "AP2 demo mandate verified" or "AP2-style signed mandate verified", not "production AP2 compliant".

## Sources Used

Official AP2 docs used for this plan:

- https://ap2-protocol.org/
- https://ap2-protocol.org/ap2/specification/
- https://ap2-protocol.org/ap2/payment_mandate/
- https://ap2-protocol.org/ap2/flows/

Relevant AP2 facts applied here:

- AP2 uses tamper-evident, cryptographically signed digital objects as transaction credentials.
- AP2 defines Checkout Mandates and Payment Mandates.
- AP2 supports Human Present and Human Not Present flows.
- In Human Present mode, the user directly approves closed Checkout and Payment Mandates.
- The Trusted Surface must be deterministic and must not rely on LLM reasoning for mandate verification.

## Product Demo Flow

The next sprint should expose two user checkpoints.

### Checkpoint 1: Authorize Agent Payment

Purpose:

- Let the user acknowledge that the agent may prepare a hotel booking payment within the visible constraints.
- This can remain UI-only in the first frontend pass, because the final AP2 signed mandate happens at Checkpoint 2.

Visible data:

- Selected hotel name.
- Dates.
- Guests.
- Maximum hotel budget.
- Agent payment amount: `0.01 USDC`.
- Network: Base Sepolia.
- Seller/payee address.
- Statement: "Hotel reservation is mock. Testnet USDC payment may be real."

### Checkpoint 2: Confirm Hotel Booking

Purpose:

- This is the real human-in-the-loop gate.
- Clicking this creates a signed AP2 demo mandate bundle.
- The booking call must fail closed if this signed bundle is missing, expired, tampered, or mismatched.

Visible data:

- Hotel.
- Room type.
- Cancellation policy.
- Stay dates and nights.
- Guests.
- Estimated stay price.
- x402 agent fee.
- Payer and payee.
- Network and token.
- Mock hotel booking disclaimer.

Button label:

```text
Confirm Hotel Booking
```

After success, the panel should show:

- AP2 status: `verified`.
- x402 status: `settled` or `simulated`, depending on env.
- BaseScan transaction link when `payment.status="settled"`.
- Booking status: `mock_confirmed`.

## Backend Design

### New Environment Variables

Add these to `docs/reference/agentic-payments.md` and mention them in `.env` docs without committing secret values:

```bash
AP2_MODE=disabled
AP2_MODE=demo_signed
AP2_DEMO_SIGNING_SECRET=local-demo-secret-for-tripcanvas-ap2
AP2_DEMO_ISSUER=tripcanvas-demo-trusted-surface
AP2_DEMO_AUDIENCE=tripcanvas-hotel-booking-agent
AP2_MANDATE_TTL_SECONDS=300
```

Behavior:

- `AP2_MODE=disabled`: preserve current local/offline behavior.
- `AP2_MODE=demo_signed`: `/hotel-booking` requires a valid signed AP2 mandate bundle.
- Missing `AP2_DEMO_SIGNING_SECRET` in `demo_signed` mode returns a stable rejected response before x402.
- Real x402 must never run if AP2 verification fails.

### Signed Mandate Shape

Create a compact JWS-like object using standard-library HMAC-SHA256. This avoids adding dependencies and is enough for a demo cryptographic proof.

Response object:

```json
{
  "format": "tripcanvas-ap2-demo-jws",
  "protected": "base64url-json-header",
  "payload": "base64url-json-payload",
  "signature": "base64url-hmac-sha256",
  "payload_json": {
    "vct": "tripcanvas.ap2.hotel_booking.confirmation.1",
    "mode": "direct",
    "issuer": "tripcanvas-demo-trusted-surface",
    "audience": "tripcanvas-hotel-booking-agent",
    "mandate_id": "ap2-demo-tc-demo-osaka-001",
    "trip_id": "tc-demo-osaka-001",
    "idempotency_key": "tc-demo-osaka-001:ap2-demo-tc-demo-osaka-001:hotel_royal_park_shiodome",
    "checkout": {
      "checkout_id": "checkout_hotel_royal_park_shiodome_20260610",
      "checkout_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
      "hotel_id": "hotel_royal_park_shiodome",
      "hotel_name": "The Royal Park Hotel Iconic Tokyo Shiodome",
      "city": "Tokyo",
      "checkin": "2026-06-10",
      "checkout": "2026-06-13",
      "nights": 3,
      "guests": 2,
      "estimated_total_sgd": 600,
      "mock_booking_only": true
    },
    "payment": {
      "protocol": "x402",
      "network": "eip155:84532",
      "asset": "USDC",
      "amount": "0.01",
      "payer": "0x407F9c97a9CE80a9fa95765c861BC6dfe8eBEDD4",
      "payee": "0x009e5eC03b638194DF3F10f158d311883cBFE5B7",
      "payment_request_id": "x402_mock_7df63c178ad5"
    },
    "constraints": {
      "allowed_action": "mock_hotel_booking",
      "max_total_sgd": 650,
      "max_agent_payment_usd": "0.01",
      "requires_user_visible_receipt": true
    },
    "confirmation": {
      "confirmation_id": "ap2_confirm_8e7d4c90a312",
      "confirmed_at": "2026-06-06T04:45:00Z",
      "trusted_surface": "tripcanvas-web",
      "button_label": "Confirm Hotel Booking"
    },
    "iat": 1780710000,
    "exp": 1780710300,
    "nonce": "ap2_nonce_5cbe752fe8d4"
  }
}
```

Implementation notes:

- `protected` header should include `alg="HS256"`, `typ="JWT"`, and `kid="tripcanvas-demo-ap2-v1"`.
- `payload_json` is included in API responses for demo readability, but verification must use the encoded `protected.payload.signature` fields.
- Use canonical JSON with sorted keys and compact separators before base64url encoding.
- `checkout_hash` should be a SHA-256 hash over the canonical checkout object.
- Never log the full signature or full signed payload in production-like logs.

### Verification Rules

When `AP2_MODE=demo_signed`, reject before x402 if any rule fails:

- Missing signed AP2 mandate.
- Missing AP2 signing secret.
- Unsupported `format`, `alg`, `typ`, `kid`, or `vct`.
- Invalid HMAC signature.
- Expired `exp`.
- Future `iat` beyond a small clock-skew allowance of 60 seconds.
- Wrong `trip_id`.
- Wrong `idempotency_key`.
- Wrong `mandate_id`.
- Wrong `hotel_id`.
- Wrong action; must be `mock_hotel_booking`.
- `mock_booking_only` is not true.
- Wrong network.
- Wrong asset.
- Wrong amount.
- Wrong payer.
- Wrong payee.
- Wrong `payment_request_id`.
- Checkout hash does not match the checkout payload.
- `confirmation.button_label` is not `Confirm Hotel Booking`.

Stable error codes:

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

### Receipt Shape

Keep the existing `/hotel-booking` response stable, but add optional AP2 fields.

Add to `HotelBookingResponse`:

```json
{
  "ap2": {
    "status": "verified",
    "mode": "direct",
    "mandate_id": "ap2-demo-tc-demo-osaka-001",
    "checkout_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "confirmation_id": "ap2_confirm_8e7d4c90a312",
    "confirmed_at": "2026-06-06T04:45:00Z",
    "issuer": "tripcanvas-demo-trusted-surface"
  }
}
```

Add to `HotelBookingReceipt`:

```json
{
  "ap2": {
    "status": "verified",
    "mode": "direct",
    "mandate_id": "ap2-demo-tc-demo-osaka-001",
    "checkout_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "confirmation_id": "ap2_confirm_8e7d4c90a312"
  }
}
```

Audit events should include:

```text
ap2_mandate_created
ap2_mandate_verified
payment_required
payment_completed
booking_confirmed
```

If AP2 fails:

```text
ap2_mandate_rejected
```

Do not include any `payment_completed` event when AP2 fails.

## API Design

### POST /ap2/hotel-booking-mandate

Purpose:

- Build the exact final hotel checkout/payment terms.
- Return a signed AP2 demo mandate bundle.
- Does not perform x402 settlement.
- Does not create a booking.

Request:

```json
{
  "trip_id": "tc-demo-osaka-001",
  "hotel_base": {},
  "mandate": {},
  "idempotency_key": "tc-demo-osaka-001:ap2-demo-tc-demo-osaka-001:hotel_royal_park_shiodome",
  "user_confirmation": {
    "confirmed": true,
    "button_label": "Confirm Hotel Booking",
    "trusted_surface": "tripcanvas-web"
  }
}
```

Response:

```json
{
  "status": "signed",
  "ap2": {
    "status": "created",
    "mode": "direct",
    "mandate_id": "ap2-demo-tc-demo-osaka-001",
    "checkout_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
    "confirmation_id": "ap2_confirm_8e7d4c90a312",
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

Failure response:

```json
{
  "status": "rejected",
  "ap2": null,
  "preview": null,
  "error": {
    "code": "ap2_confirmation_required",
    "message": "User must confirm the hotel booking before an AP2 mandate can be signed."
  }
}
```

### POST /hotel-booking

Extend request:

```json
{
  "trip_id": "tc-demo-osaka-001",
  "hotel_base": {},
  "mandate": {},
  "idempotency_key": "tc-demo-osaka-001:ap2-demo-tc-demo-osaka-001:hotel_royal_park_shiodome",
  "ap2_signed_mandate": {}
}
```

Behavior:

- In `AP2_MODE=disabled`, current behavior remains available.
- In `AP2_MODE=demo_signed`, backend verifies `ap2_signed_mandate` before creating x402 payment proof.
- If AP2 verifies, run existing x402 simulation/real adapter.
- If AP2 fails, return `status="rejected"` with AP2 error code.

## File Map

Backend:

- Modify `backend/spike_agentic_payments.py`
  - Add AP2 Pydantic models.
  - Add demo signing and verification helpers.
  - Add AP2 mandate creation function.
  - Add optional AP2 fields to booking request/response/receipt.
  - Enforce AP2 verification in `AgenticHotelPaymentService.run_payment_loop` when enabled.

- Modify `backend/main.py`
  - Register `POST /ap2/hotel-booking-mandate`.
  - Keep `POST /hotel-booking` response shape backward-compatible.

- Modify `backend/tests/test_agentic_hotel_payments.py`
  - Add AP2 mandate creation tests.
  - Add AP2 verification tests.
  - Add fail-closed tests for missing/tampered/expired/mismatched mandate.
  - Add "AP2 failure does not run x402" regression test.

- Modify `docs/reference/agentic-payments.md`
  - Add AP2 signed human-in-loop section and env vars.
  - Clarify demo AP2 is not production AP2 compliance.

Frontend:

- Modify `frontend/lib/trip/backend-types.ts`
  - Add AP2 signed mandate request/response types.
  - Add hotel booking request/response/payment/receipt types.

- Modify `frontend/lib/trip/generate-trip.ts`
  - Add `createHotelBookingMandate`.
  - Add `bookHotelWithAp2Mandate`.
  - Add BaseScan URL helper for Base Sepolia tx hashes.

- Modify `frontend/components/trip/TripGenerationShell.tsx`
  - Add state for AP2 authorization, signed mandate, booking status, and errors.
  - Add handlers for "Authorize Agent Payment" and "Confirm Hotel Booking".
  - Call `/ap2/hotel-booking-mandate`, then `/hotel-booking`.

- Modify or create `frontend/components/trip/HotelPaymentPanel.tsx`
  - Prefer creating this focused component if `TripGenerationShell.tsx` becomes too dense.
  - Render AP2/x402 state, final confirmation, receipt, and tx link.

## Task 1: Backend AP2 Models And Signing

**Files:**

- Modify: `backend/spike_agentic_payments.py`
- Test: `backend/tests/test_agentic_hotel_payments.py`

- [ ] **Step 1: Write failing tests for signed mandate creation**

Add tests:

```python
def test_ap2_demo_mandate_creation_requires_user_confirmation(self):
    with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
        response = create_ap2_hotel_booking_mandate(
            demo_request(),
            user_confirmation={"confirmed": False, "button_label": "Confirm Hotel Booking"},
        )

    self.assertEqual(response.status, "rejected")
    self.assertEqual(response.error.code, "ap2_confirmation_required")


def test_ap2_demo_mandate_creation_returns_signed_bundle(self):
    with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
        response = create_ap2_hotel_booking_mandate(
            demo_request(),
            user_confirmation={
                "confirmed": True,
                "button_label": "Confirm Hotel Booking",
                "trusted_surface": "tripcanvas-web",
            },
        )

    self.assertEqual(response.status, "signed")
    self.assertEqual(response.ap2.status, "created")
    self.assertEqual(response.ap2.signed_mandate.payload_json["vct"], "tripcanvas.ap2.hotel_booking.confirmation.1")
    self.assertEqual(response.ap2.signed_mandate.payload_json["checkout"]["hotel_id"], "hotel_royal_park_shiodome")
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mandate_creation_requires_user_confirmation -v
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mandate_creation_returns_signed_bundle -v
```

Expected:

- Tests fail because AP2 models/functions do not exist.

- [ ] **Step 3: Add AP2 models and signing helpers**

Add models:

```python
class AP2UserConfirmation(BaseModel):
    confirmed: bool = False
    button_label: str
    trusted_surface: str = "tripcanvas-web"


class AP2SignedMandate(BaseModel):
    format: Literal["tripcanvas-ap2-demo-jws"] = "tripcanvas-ap2-demo-jws"
    protected: str
    payload: str
    signature: str
    payload_json: dict[str, Any]


class AP2MandateSummary(BaseModel):
    status: Literal["created", "verified", "rejected"]
    mode: Literal["direct"] = "direct"
    mandate_id: str
    checkout_hash: str
    confirmation_id: str
    confirmed_at: datetime
    issuer: str
    signed_mandate: Optional[AP2SignedMandate] = None


class AP2MandateResponse(BaseModel):
    status: Literal["signed", "rejected"]
    ap2: Optional[AP2MandateSummary] = None
    preview: Optional[dict[str, Any]] = None
    error: Optional[BookingError] = None
```

Add helpers:

```python
def _ap2_mode() -> str:
    return os.getenv("AP2_MODE", "disabled").strip().lower() or "disabled"


def _ap2_demo_secret() -> str:
    secret = os.getenv("AP2_DEMO_SIGNING_SECRET", "").strip()
    if not secret:
        raise ConstraintViolation("ap2_config_missing", "AP2_DEMO_SIGNING_SECRET is required when AP2_MODE=demo_signed.")
    return secret
```

Use `json.dumps(..., sort_keys=True, separators=(",", ":"), default=str)`, `base64.urlsafe_b64encode(...).rstrip(b"=")`, `hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mandate_creation_requires_user_confirmation -v
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mandate_creation_returns_signed_bundle -v
```

Expected:

- Both pass.

- [ ] **Step 5: Commit**

```bash
git add backend/spike_agentic_payments.py backend/tests/test_agentic_hotel_payments.py
git commit -m "feat(backend): add AP2 demo mandate signing"
```

## Task 2: Backend AP2 Verification Before x402

**Files:**

- Modify: `backend/spike_agentic_payments.py`
- Test: `backend/tests/test_agentic_hotel_payments.py`

- [ ] **Step 1: Write failing tests for fail-closed verification**

Add tests:

```python
def test_ap2_demo_mode_requires_signed_mandate_before_x402(self):
    with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
        response = AgenticHotelPaymentService().run_payment_loop(demo_request())

    self.assertEqual(response.status, "rejected")
    self.assertEqual(response.error.code, "ap2_mandate_required")
    self.assertIsNone(response.payment)
    self.assertIsNone(response.receipt)


def test_ap2_tampered_mandate_rejects_before_x402(self):
    with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
        signed = create_ap2_hotel_booking_mandate(
            demo_request(),
            user_confirmation={
                "confirmed": True,
                "button_label": "Confirm Hotel Booking",
                "trusted_surface": "tripcanvas-web",
            },
        ).ap2.signed_mandate
        tampered = signed.model_copy(
            update={
                "payload_json": {
                    **signed.payload_json,
                    "payment": {**signed.payload_json["payment"], "amount": "0.02"},
                }
            }
        )
        response = AgenticHotelPaymentService().run_payment_loop(
            demo_request(ap2_signed_mandate=tampered)
        )

    self.assertEqual(response.status, "rejected")
    self.assertEqual(response.error.code, "ap2_signature_invalid")
    self.assertIsNone(response.payment)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mode_requires_signed_mandate_before_x402 -v
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_tampered_mandate_rejects_before_x402 -v
```

Expected:

- Tests fail because booking request does not include AP2 fields and service does not enforce AP2 verification.

- [ ] **Step 3: Extend request/response models**

Modify `HotelBookingRequest`:

```python
class HotelBookingRequest(BaseModel):
    trip_id: str = _DEFAULT_TRIP_ID
    hotel_base: Optional[dict[str, Any]] = None
    mandate: Optional[BookingMandate] = None
    idempotency_key: Optional[str] = None
    ap2_signed_mandate: Optional[AP2SignedMandate] = None
```

Modify `HotelBookingResponse` and `HotelBookingReceipt` with optional `ap2: Optional[AP2MandateSummary] = None`.

- [ ] **Step 4: Verify AP2 before payment**

In `AgenticHotelPaymentService.run_payment_loop`, after `first_attempt` normalizes/builds context and before `create_payment_proof`, verify AP2 when `_ap2_mode() == "demo_signed"`.

Verification should compare the signed payload against:

- normalized `trip_id`
- normalized `idempotency_key`
- `context.mandate.mandate_id`
- selected hotel id
- `PaymentInstructions.amount`
- `PaymentInstructions.network`
- `PaymentInstructions.asset`
- `PaymentInstructions.payer`
- `PaymentInstructions.payee`
- `PaymentInstructions.payment_request_id`

Return `_rejected(ConstraintViolation(...))` on failure. Do not call `self.payment_adapter.create_payment_proof` when verification fails.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_demo_mode_requires_signed_mandate_before_x402 -v
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_tampered_mandate_rejects_before_x402 -v
```

Expected:

- Both pass.

- [ ] **Step 6: Commit**

```bash
git add backend/spike_agentic_payments.py backend/tests/test_agentic_hotel_payments.py
git commit -m "feat(backend): require AP2 mandate before hotel payment"
```

## Task 3: AP2 Mandate Endpoint

**Files:**

- Modify: `backend/main.py`
- Modify: `backend/spike_agentic_payments.py`
- Test: `backend/tests/test_agentic_hotel_payments.py`

- [ ] **Step 1: Write failing HTTP endpoint tests**

Add tests:

```python
def test_ap2_hotel_booking_mandate_endpoint_signs_preview(self):
    with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
        response = TestClient(app).post(
            "/ap2/hotel-booking-mandate",
            json={
                **demo_request().model_dump(mode="json"),
                "user_confirmation": {
                    "confirmed": True,
                    "button_label": "Confirm Hotel Booking",
                    "trusted_surface": "tripcanvas-web",
                },
            },
        )

    self.assertEqual(response.status_code, 200)
    body = response.json()
    self.assertEqual(body["status"], "signed")
    self.assertEqual(body["ap2"]["status"], "created")
    self.assertEqual(body["preview"]["payment"]["amount"], "0.01")
```

- [ ] **Step 2: Run test and verify failure**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_hotel_booking_mandate_endpoint_signs_preview -v
```

Expected:

- Fails with 404 because endpoint does not exist.

- [ ] **Step 3: Add endpoint**

In `backend/main.py` import request/response models and register:

```python
@app.post("/ap2/hotel-booking-mandate", response_model=AP2MandateResponse)
def ap2_hotel_booking_mandate(req: AP2MandateRequest) -> AP2MandateResponse:
    return create_ap2_hotel_booking_mandate(req)
```

The request model should include the existing booking request fields plus `user_confirmation`.

- [ ] **Step 4: Run endpoint test**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments.AgenticHotelPaymentTests.test_ap2_hotel_booking_mandate_endpoint_signs_preview -v
```

Expected:

- Pass.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/spike_agentic_payments.py backend/tests/test_agentic_hotel_payments.py
git commit -m "feat(backend): expose AP2 hotel mandate endpoint"
```

## Task 4: Frontend Types And API Client

**Files:**

- Modify: `frontend/lib/trip/backend-types.ts`
- Modify: `frontend/lib/trip/generate-trip.ts`

- [ ] **Step 1: Add TypeScript types**

Add:

```ts
export type AP2SignedMandate = {
  format: "tripcanvas-ap2-demo-jws";
  protected: string;
  payload: string;
  signature: string;
  payload_json: Record<string, unknown>;
};

export type AP2MandateSummary = {
  status: "created" | "verified" | "rejected";
  mode: "direct";
  mandate_id: string;
  checkout_hash: string;
  confirmation_id: string;
  confirmed_at: string;
  issuer: string;
  signed_mandate?: AP2SignedMandate | null;
};

export type AP2MandateResponse = {
  status: "signed" | "rejected";
  ap2: AP2MandateSummary | null;
  preview: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
};

export type HotelBookingResponse = {
  status: "payment_required" | "mock_confirmed" | "rejected" | "payment_failed";
  ap2?: AP2MandateSummary | null;
  payment?: {
    protocol: "x402";
    network: string;
    asset: string;
    amount: string;
    payer: string;
    payee: string;
    tx_hash: string;
    status: "simulated" | "settled";
  } | null;
  receipt?: Record<string, unknown> | null;
  error?: { code: string; message: string } | null;
};
```

- [ ] **Step 2: Add API functions**

In `frontend/lib/trip/generate-trip.ts`:

```ts
export async function createHotelBookingMandate(payload: unknown): Promise<AP2MandateResponse> {
  const response = await fetch(`${getBackendBaseUrl()}/ap2/hotel-booking-mandate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`AP2 mandate failed with HTTP ${response.status}.`);
  }
  return response.json() as Promise<AP2MandateResponse>;
}

export async function bookHotelWithAp2Mandate(payload: unknown): Promise<HotelBookingResponse> {
  const response = await fetch(`${getBackendBaseUrl()}/hotel-booking`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Hotel booking failed with HTTP ${response.status}.`);
  }
  return response.json() as Promise<HotelBookingResponse>;
}

export function getBaseSepoliaTxUrl(txHash: string) {
  return `https://sepolia.basescan.org/tx/${encodeURIComponent(txHash)}`;
}
```

- [ ] **Step 3: Run typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected:

- Pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/trip/backend-types.ts frontend/lib/trip/generate-trip.ts
git commit -m "feat(frontend): add AP2 hotel booking API client"
```

## Task 5: Frontend Human-In-The-Loop Panel

**Files:**

- Create: `frontend/components/trip/HotelPaymentPanel.tsx`
- Modify: `frontend/components/trip/TripGenerationShell.tsx`

- [ ] **Step 1: Create `HotelPaymentPanel`**

The component should render four compact states:

```text
AP2 mandate: not signed | signed | verified | rejected
x402 payment: idle | simulated | settled | failed
Hotel booking: not started | mock confirmed | rejected
Safety: mock hotel reservation, testnet payment may be real
```

Buttons:

```text
Authorize Agent Payment
Confirm Hotel Booking
```

Button behavior:

- `Authorize Agent Payment` should set local UI state only.
- `Confirm Hotel Booking` should call `createHotelBookingMandate`, then call `bookHotelWithAp2Mandate` with the returned `signed_mandate`.

Required copy:

```text
No real hotel reservation will be created.
If real x402 mode is enabled, testnet USDC may move.
```

For settled x402 payments, render:

```tsx
<a href={getBaseSepoliaTxUrl(txHash)} target="_blank" rel="noreferrer">
  View Base Sepolia transaction
</a>
```

- [ ] **Step 2: Wire panel into right agent panel**

In `TripGenerationShell.tsx`, show `HotelPaymentPanel` after hotel-base optimization has produced `activeTrip.hotelBase` or after final trip has `hotelBase`.

Do not block itinerary generation in this sprint unless the user explicitly wants the booking to happen before itinerary planning. For demo simplicity, booking can be a right-panel action after the selected hotel exists.

- [ ] **Step 3: Add state and handlers**

State:

```ts
const [hotelPaymentState, setHotelPaymentState] = useState<{
  authorized: boolean;
  signedMandate: AP2SignedMandate | null;
  mandateResponse: AP2MandateResponse | null;
  bookingResponse: HotelBookingResponse | null;
  error: string | null;
  isRunning: boolean;
}>({
  authorized: false,
  signedMandate: null,
  mandateResponse: null,
  bookingResponse: null,
  error: null,
  isRunning: false,
});
```

Handler:

```ts
async function handleConfirmHotelBooking() {
  if (!activeTrip.hotelBase || !preferences) {
    setHotelPaymentState((state) => ({ ...state, error: "Select a hotel base before booking." }));
    return;
  }
  setHotelPaymentState((state) => ({ ...state, isRunning: true, error: null }));
  try {
    const mandateResponse = await createHotelBookingMandate({
      trip_id: "tc-demo-osaka-001",
      hotel_base: activeTrip.hotelBase,
      idempotency_key: `tc-demo-osaka-001:${activeTrip.hotelBase.selected_hotel_id}:demo`,
      user_confirmation: {
        confirmed: true,
        button_label: "Confirm Hotel Booking",
        trusted_surface: "tripcanvas-web",
      },
    });
    if (!mandateResponse.ap2?.signed_mandate) {
      throw new Error(mandateResponse.error?.message || "AP2 mandate was not signed.");
    }
    const bookingResponse = await bookHotelWithAp2Mandate({
      trip_id: "tc-demo-osaka-001",
      hotel_base: activeTrip.hotelBase,
      idempotency_key: `tc-demo-osaka-001:${activeTrip.hotelBase.selected_hotel_id}:demo`,
      ap2_signed_mandate: mandateResponse.ap2.signed_mandate,
    });
    setHotelPaymentState((state) => ({
      ...state,
      signedMandate: mandateResponse.ap2?.signed_mandate ?? null,
      mandateResponse,
      bookingResponse,
      isRunning: false,
    }));
  } catch (error) {
    setHotelPaymentState((state) => ({
      ...state,
      error: error instanceof Error ? error.message : "Hotel booking failed.",
      isRunning: false,
    }));
  }
}
```

Adjust exact property names to match `TripHotelBase` from `frontend/lib/trip/types.ts` when implementing.

- [ ] **Step 4: Run frontend typecheck**

Run:

```bash
cd frontend && npm run typecheck
```

Expected:

- Pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/trip/HotelPaymentPanel.tsx frontend/components/trip/TripGenerationShell.tsx
git commit -m "feat(frontend): add AP2 hotel confirmation panel"
```

## Task 6: Docs, Demo Commands, And End-To-End Checks

**Files:**

- Modify: `docs/reference/agentic-payments.md`
- Modify: this AP2 plan file

- [ ] **Step 1: Update docs**

Add:

- AP2 demo env vars.
- Explicit note that AP2 demo signing is not full AP2 compliance.
- Human-present direct flow explanation.
- Real x402 warning: every successful real call spends `0.01` testnet USDC.

- [ ] **Step 2: Backend verification**

Run:

```bash
uv run python -m unittest backend.tests.test_agentic_hotel_payments -v
uv run python -m unittest discover -s backend/tests -v
git diff --check
```

Expected:

- All tests pass.
- No whitespace errors.

- [ ] **Step 3: Frontend verification**

Run:

```bash
cd frontend && npm run typecheck
```

Expected:

- TypeScript passes.

- [ ] **Step 4: Offline demo smoke**

Run backend with simulation mode:

```bash
AP2_MODE=demo_signed \
AP2_DEMO_SIGNING_SECRET=local-demo-secret \
X402_MODE=simulation \
HOTEL_BOOKING_MODE=mock \
uv run uvicorn backend.main:app --port 8000
```

In another terminal, run frontend:

```bash
cd frontend && npm run dev
```

Manual acceptance:

- Hotel/base recommendation is visible.
- User can click "Authorize Agent Payment".
- User can click "Confirm Hotel Booking".
- UI shows AP2 signed/verified.
- UI shows x402 simulated.
- UI shows mock booking receipt.
- UI warning says no real hotel reservation was created.

- [ ] **Step 5: Real x402 smoke**

Only run after the wallet is funded and the user explicitly approves spending another `0.01` testnet USDC.

```bash
AP2_MODE=demo_signed \
AP2_DEMO_SIGNING_SECRET=local-demo-secret-for-tripcanvas-ap2 \
X402_MODE=real \
X402_NETWORK=eip155:84532 \
HOTEL_BOOKING_MODE=mock \
uv run uvicorn backend.main:app --port 8000
```

Expected:

- Booking response `status="mock_confirmed"`.
- `ap2.status="verified"`.
- `payment.status="settled"`.
- `payment.tx_hash` does not start with `0xSIMULATED`.
- BaseScan Token Transfers tab shows `0.01` USDC from payer to payee.

This command assumes `ORCHESTRATOR_PRIVATE_KEY`, `ORCHESTRATOR_WALLET_ADDRESS`, and `HOTEL_AGENT_PAY_TO` are already present in the local shell or loaded from `.env`.

- [ ] **Step 6: Commit docs**

```bash
git add docs/reference/agentic-payments.md docs/superpowers/plans/2026-06-06-ap2-human-in-the-loop.md
git commit -m "docs: plan AP2 human-in-the-loop hotel booking"
```

## Acceptance Criteria

Backend:

- In default mode, existing tests keep passing.
- In `AP2_MODE=demo_signed`, `/hotel-booking` rejects missing AP2 mandate.
- Tampered AP2 signed payload rejects before x402.
- Expired AP2 signed payload rejects before x402.
- AP2 hotel id mismatch rejects before x402.
- AP2 amount/network/payee mismatch rejects before x402.
- Valid AP2 signed mandate allows existing x402 simulation path.
- Valid AP2 signed mandate allows real x402 path when real env is configured.

Frontend:

- User sees selected hotel and final payment terms before confirmation.
- User must click a visible "Confirm Hotel Booking" control before `/hotel-booking`.
- UI clearly separates AP2 authorization status from x402 settlement status.
- UI links settled tx hash to Base Sepolia explorer.
- UI states no real hotel reservation was created.

Demo story:

```text
The user did not give a blank cheque.
They confirmed a specific mock hotel checkout.
AP2 signed the human confirmation.
The backend verified the AP2 mandate.
x402 settled the agent payment.
TripCanvas issued a mock hotel receipt.
```

## Rollback Plan

If AP2 demo signing destabilizes the demo:

1. Set `AP2_MODE=disabled`.
2. Keep `X402_MODE=simulation` or `X402_MODE=real` as needed.
3. `/hotel-booking` returns to the current behavior.
4. Leave the frontend AP2 panel hidden behind a feature flag or only show read-only mandate state.

Do not remove the x402 implementation. AP2 is an authorization gate layered above x402, not a replacement for x402.

## Open Decisions For The Next Session

The next implementer should choose one of these before coding:

1. **Default AP2 mode**
   - Recommended: keep `AP2_MODE=disabled` by default for offline tests, and set `AP2_MODE=demo_signed` in demo env.

2. **Signing model**
   - Recommended: backend Trusted Surface HMAC signer for minimal demo.
   - Stronger but more work: browser Web Crypto signs with an ephemeral public key, backend verifies public JWK plus signature. This still is not production AP2 identity because there is no credential enrollment.

3. **Booking timing**
   - Recommended: make hotel booking a right-panel action after hotel-base selection, not a blocker before itinerary planning.
   - More dramatic but riskier: require AP2/x402 booking before final itinerary generation.

4. **PR scope**
   - Recommended: backend AP2 first, then frontend panel in a second commit or second PR if time is tight.
