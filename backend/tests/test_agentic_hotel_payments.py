import base64
import copy
import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.spike_agentic_payments import (
    AgenticHotelPaymentService,
    BookingMandate,
    HotelBookingRequest,
    X402RealAdapter,
    X402SimulationAdapter,
    create_ap2_hotel_booking_mandate,
    load_hotel_tool_dict,
    resolve_selected_hotel,
    _sign_ap2_payload,
)


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class FakeX402Binding:
    def __init__(self, *, fail_settlement: bool = False):
        self.fail_settlement = fail_settlement
        self.requirements_config = None
        self.payment_payload = {"signed": "payload"}

    def build_payment_requirements(self, **config):
        self.requirements_config = config
        return [{"network": config["network"], "payTo": config["pay_to"]}]

    def create_payment_payload(self, requirements):
        return self.payment_payload

    def verify_and_settle(self, payload, requirements):
        if self.fail_settlement:
            return {"success": False, "error": "facilitator rejected payment"}
        return {"success": True, "tx_hash": "0xREALX402SETTLED"}


class RecordingPaymentAdapter(X402SimulationAdapter):
    def __init__(self):
        super().__init__()
        self.create_payment_proof_called = False

    def create_payment_proof(self, request, instructions):
        self.create_payment_proof_called = True
        return super().create_payment_proof(request, instructions)


def booking_ready_hotel_tool() -> dict:
    with (DATA_DIR / "planner_output.json").open(encoding="utf-8") as fh:
        hotel_tool = json.load(fh)

    hotel_tool = copy.deepcopy(hotel_tool)
    hotel_tool["payment_context"] = {
        "payment_protocol": "x402",
        "network": "base-sepolia",
        "asset": "USDC",
        "agent_payment_usd": "0.01",
        "mock_booking_only": True,
    }
    for hotel in hotel_tool["hotel_options"]:
        if hotel.get("is_best") is True:
            hotel.update(
                {
                    "city": "Tokyo",
                    "area": "Shiodome",
                    "lat": 35.6655,
                    "lng": 139.7585,
                    "price_per_night_sgd": 200,
                    "station_walk_min": 6,
                    "convenience_store_walk_min": 2,
                    "quiet_score": 8,
                    "route_efficiency_score": 9,
                    "budget_tier": "mid_range",
                    "amenities": ["breakfast", "near_station", "laundry"],
                    "mock_available_rooms": 3,
                    "room_type": "Standard double room",
                    "cancellation_policy": "Free cancellation until 48 hours before check-in",
                }
            )
    return hotel_tool


def demo_mandate(**overrides) -> BookingMandate:
    data = {
        "mandate_id": "ap2-demo-tc-osaka-001",
        "mode": "autonomous",
        "allowed_action": "mock_hotel_booking",
        "city": "Tokyo",
        "checkin": "2026-06-10",
        "checkout": "2026-06-13",
        "guests": 2,
        "budget": "mid_range",
        "hotel_preferences": ["near_station", "quiet", "near_convenience_store"],
        "max_total_sgd": 650,
        "max_agent_payment_usd": "0.01",
        "payment_protocol": "x402",
        "network": "base-sepolia",
        "expires_at": "2030-06-10T00:00:00Z",
        "requires_user_visible_receipt": True,
        "mock_booking_only": True,
    }
    data.update(overrides)
    return BookingMandate.model_validate(data)


def demo_request(**overrides) -> HotelBookingRequest:
    data = {
        "trip_id": "tc-demo-osaka-001",
        "hotel_base": booking_ready_hotel_tool(),
        "mandate": demo_mandate(),
        "idempotency_key": (
            "tc-demo-osaka-001:ap2-demo-tc-osaka-001:"
            "hotel_royal_park_shiodome"
        ),
    }
    data.update(overrides)
    return HotelBookingRequest.model_validate(data)


def real_demo_request(**overrides) -> HotelBookingRequest:
    data = {
        "mandate": demo_mandate(network="eip155:84532"),
    }
    data.update(overrides)
    return demo_request(**data)


def signed_demo_mandate():
    response = create_ap2_hotel_booking_mandate(
        demo_request(),
        user_confirmation={
            "confirmed": True,
            "button_label": "Confirm Hotel Booking",
            "trusted_surface": "tripcanvas-web",
        },
    )
    return response.ap2.signed_mandate


def tamper_encoded_payload(signed_mandate, mutator):
    payload = _decode_test_payload(signed_mandate.payload)
    mutator(payload)
    tampered_payload = _base64url_json(payload)
    return signed_mandate.model_copy(
        update={
            "payload": tampered_payload,
            "payload_json": payload,
        }
    )


def resign_payload(signed_mandate, mutator):
    payload = _decode_test_payload(signed_mandate.payload)
    mutator(payload)
    return _sign_ap2_payload(payload)


def _decode_test_payload(encoded):
    padding = "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode((encoded + padding).encode()).decode())


def _base64url_json(payload):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class AgenticHotelPaymentTests(unittest.TestCase):
    def test_planner_output_loads_and_resolves_best_hotel_option(self):
        hotel_tool = load_hotel_tool_dict()

        selected_hotel = resolve_selected_hotel(hotel_tool)

        self.assertIn("hotel_options", hotel_tool)
        self.assertEqual(selected_hotel["id"], "hotel_royal_park_shiodome")
        self.assertEqual(selected_hotel["name"], "The Royal Park Hotel Iconic Tokyo Shiodome")
        self.assertIs(selected_hotel["is_best"], True)

    def test_booking_requires_payment_before_proof(self):
        service = AgenticHotelPaymentService()
        request = demo_request()

        response = service.attempt_booking(request)

        self.assertEqual(response.status, "payment_required")
        self.assertIsNone(response.receipt)
        self.assertIsNotNone(response.payment_required)
        self.assertEqual(response.payment_required.protocol, "x402")
        self.assertEqual(response.payment_required.amount, "0.01")
        self.assertEqual(
            [event.type for event in response.audit_events],
            ["mandate_validated", "payment_required"],
        )

    def test_orchestrator_pays_retries_and_returns_deterministic_mock_receipt(self):
        service = AgenticHotelPaymentService()
        request = demo_request()

        first = service.run_payment_loop(request)
        second = service.run_payment_loop(request)

        expected_booking_id = (
            "TC-MOCK-HOTEL-"
            + hashlib.sha1(
                "tc-demo-osaka-001|ap2-demo-tc-osaka-001|"
                "hotel_royal_park_shiodome|2026-06-10|2026-06-13|2".encode()
            )
            .hexdigest()[:8]
            .upper()
        )
        self.assertEqual(first.status, "mock_confirmed")
        self.assertEqual(first.receipt.booking_id, expected_booking_id)
        self.assertEqual(first.receipt.status, "mock_confirmed")
        self.assertTrue(first.receipt.is_mock)
        self.assertIn("No real hotel reservation was created", first.receipt.receipt_note)
        self.assertEqual(first.payment.status, "simulated")
        self.assertEqual(first.payment.tx_hash, second.payment.tx_hash)
        self.assertEqual(first.receipt.booking_id, second.receipt.booking_id)
        self.assertEqual(
            [event.type for event in first.audit_events],
            [
                "mandate_validated",
                "payment_required",
                "payment_completed",
                "booking_confirmed",
            ],
        )

    def test_mandate_and_booking_constraints_fail_closed_without_receipt(self):
        cases = [
            (
                "wrong action",
                {"mandate": demo_mandate(allowed_action="real_hotel_booking")},
                "mandate_action_not_allowed",
            ),
            (
                "non mock mandate",
                {"mandate": demo_mandate(mock_booking_only=False)},
                "mock_booking_required",
            ),
            (
                "expired mandate",
                {"mandate": demo_mandate(expires_at="2020-06-10T00:00:00Z")},
                "mandate_expired",
            ),
            (
                "over budget stay",
                {"mandate": demo_mandate(max_total_sgd=100)},
                "stay_total_exceeds_mandate",
            ),
            (
                "agent payment over mandate",
                {"mandate": demo_mandate(max_agent_payment_usd="0.005")},
                "agent_payment_exceeds_mandate",
            ),
        ]

        for name, overrides, expected_code in cases:
            with self.subTest(name=name):
                response = AgenticHotelPaymentService().run_payment_loop(
                    demo_request(**overrides)
                )

                self.assertEqual(response.status, "rejected")
                self.assertIsNone(response.receipt)
                self.assertEqual(response.error.code, expected_code)
                self.assertEqual(response.audit_events[-1].type, "booking_rejected")

    def test_hotel_booking_mode_must_stay_mock(self):
        with patch.dict(os.environ, {"HOTEL_BOOKING_MODE": "live"}):
            response = AgenticHotelPaymentService().run_payment_loop(demo_request())

        self.assertEqual(response.status, "rejected")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "hotel_booking_mode_not_mock")

    def test_selected_hotel_without_rooms_is_rejected(self):
        hotel_base = booking_ready_hotel_tool()
        for hotel in hotel_base["hotel_options"]:
            if hotel.get("is_best") is True:
                hotel["mock_available_rooms"] = 0

        response = AgenticHotelPaymentService().run_payment_loop(
            demo_request(hotel_base=hotel_base)
        )

        self.assertEqual(response.status, "rejected")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "no_mock_rooms_available")

    def test_smoke_path_missing_selected_hotel_is_rejected_without_receipt(self):
        hotel_base = booking_ready_hotel_tool()
        for hotel in hotel_base["hotel_options"]:
            hotel["is_best"] = False
        hotel_base["recommended_hotel"] = "Missing Hotel"

        response = AgenticHotelPaymentService().run_payment_loop({
            "trip_id": "tc-demo-osaka-001",
            "hotel_base": hotel_base,
        })

        self.assertEqual(response.status, "rejected")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "selected_hotel_not_found")

    def test_payment_failure_returns_audit_event_and_no_receipt(self):
        service = AgenticHotelPaymentService(
            payment_adapter=X402SimulationAdapter(simulate_failure=True)
        )

        response = service.run_payment_loop(demo_request())

        self.assertEqual(response.status, "payment_failed")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "payment_simulation_failed")
        self.assertEqual(response.audit_events[-1].type, "payment_failed")

    def test_ap2_demo_mandate_creation_requires_user_confirmation(self):
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            response = create_ap2_hotel_booking_mandate(
                demo_request(),
                user_confirmation={
                    "confirmed": False,
                    "button_label": "Confirm Hotel Booking",
                    "trusted_surface": "tripcanvas-web",
                },
            )

        self.assertEqual(response.status, "rejected")
        self.assertIsNone(response.ap2)
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
        self.assertEqual(response.ap2.signed_mandate.format, "tripcanvas-ap2-demo-jws")
        self.assertEqual(
            response.ap2.signed_mandate.payload_json["vct"],
            "tripcanvas.ap2.hotel_booking.confirmation.1",
        )
        self.assertEqual(
            response.ap2.signed_mandate.payload_json["checkout"]["hotel_id"],
            "hotel_royal_park_shiodome",
        )
        self.assertEqual(response.preview["payment"]["amount"], "0.01")

    def test_ap2_demo_mode_requires_signed_mandate_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request()
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_mandate_required")
        self.assertIsNone(response.payment)
        self.assertIsNone(response.receipt)
        self.assertFalse(adapter.create_payment_proof_called)
        self.assertNotIn("payment_completed", [event.type for event in response.audit_events])

    def test_ap2_valid_signed_mandate_allows_x402_simulation(self):
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = signed_demo_mandate()
            response = AgenticHotelPaymentService().run_payment_loop(
                demo_request(ap2_signed_mandate=signed)
            )

        self.assertEqual(response.status, "mock_confirmed")
        self.assertEqual(response.ap2.status, "verified")
        self.assertEqual(response.receipt.ap2.status, "verified")
        self.assertEqual(response.payment.status, "simulated")
        self.assertIn("ap2_mandate_verified", [event.type for event in response.audit_events])

    def test_ap2_payload_json_tampering_is_ignored_when_encoded_payload_is_valid(self):
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = signed_demo_mandate()
            tampered = signed.model_copy(
                update={
                    "payload_json": {
                        **signed.payload_json,
                        "payment": {**signed.payload_json["payment"], "amount": "999.00"},
                    }
                }
            )
            response = AgenticHotelPaymentService().run_payment_loop(
                demo_request(ap2_signed_mandate=tampered)
            )

        self.assertEqual(response.status, "mock_confirmed")
        self.assertEqual(response.ap2.status, "verified")

    def test_ap2_tampered_encoded_payload_rejects_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = signed_demo_mandate()
            tampered = tamper_encoded_payload(
                signed,
                lambda payload: payload["payment"].update({"amount": "0.02"}),
            )
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request(ap2_signed_mandate=tampered)
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_signature_invalid")
        self.assertIsNone(response.payment)
        self.assertFalse(adapter.create_payment_proof_called)

    def test_ap2_expired_mandate_rejects_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(
            os.environ,
            {
                "AP2_MODE": "demo_signed",
                "AP2_DEMO_SIGNING_SECRET": "test-secret",
                "AP2_MANDATE_TTL_SECONDS": "0",
            },
        ):
            signed = signed_demo_mandate()
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request(ap2_signed_mandate=signed)
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_mandate_expired")
        self.assertFalse(adapter.create_payment_proof_called)

    def test_ap2_future_iat_rejects_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = resign_payload(
                signed_demo_mandate(),
                lambda payload: payload.update(
                    {
                        "iat": payload["iat"] + 120,
                        "exp": payload["exp"] + 120,
                    }
                ),
            )
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request(ap2_signed_mandate=signed)
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_mandate_not_yet_valid")
        self.assertFalse(adapter.create_payment_proof_called)

    def test_ap2_payment_mismatch_rejects_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = resign_payload(
                signed_demo_mandate(),
                lambda payload: payload["payment"].update({"payee": "0xWrongSeller"}),
            )
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request(ap2_signed_mandate=signed)
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_mandate_payment_mismatch")
        self.assertFalse(adapter.create_payment_proof_called)

    def test_ap2_checkout_mismatch_rejects_before_x402(self):
        adapter = RecordingPaymentAdapter()
        with patch.dict(os.environ, {"AP2_MODE": "demo_signed", "AP2_DEMO_SIGNING_SECRET": "test-secret"}):
            signed = resign_payload(
                signed_demo_mandate(),
                lambda payload: payload["checkout"].update({"hotel_id": "hotel_wrong"}),
            )
            response = AgenticHotelPaymentService(payment_adapter=adapter).run_payment_loop(
                demo_request(ap2_signed_mandate=signed)
            )

        self.assertEqual(response.status, "rejected")
        self.assertEqual(response.error.code, "ap2_mandate_checkout_mismatch")
        self.assertFalse(adapter.create_payment_proof_called)

    def test_real_mode_selects_real_x402_adapter(self):
        with patch.dict(os.environ, {"X402_MODE": "real"}):
            service = AgenticHotelPaymentService()

        self.assertIsInstance(service.payment_adapter, X402RealAdapter)

    def test_real_mode_missing_private_key_fails_closed_without_receipt(self):
        with patch.dict(os.environ, {"X402_MODE": "real", "HOTEL_AGENT_PAY_TO": "0xSeller"}, clear=True):
            response = AgenticHotelPaymentService().run_payment_loop(real_demo_request())

        self.assertEqual(response.status, "payment_failed")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "x402_real_config_missing")
        self.assertEqual(response.audit_events[-1].type, "payment_failed")

    def test_real_mode_missing_payee_fails_closed_without_receipt(self):
        with patch.dict(os.environ, {"X402_MODE": "real", "ORCHESTRATOR_PRIVATE_KEY": "0xBuyerKey"}, clear=True):
            response = AgenticHotelPaymentService().run_payment_loop(real_demo_request())

        self.assertEqual(response.status, "payment_failed")
        self.assertIsNone(response.receipt)
        self.assertEqual(response.error.code, "x402_real_config_missing")
        self.assertEqual(response.audit_events[-1].type, "payment_failed")

    def test_real_adapter_maps_successful_settlement_to_settled_receipt(self):
        binding = FakeX402Binding()
        service = AgenticHotelPaymentService(payment_adapter=X402RealAdapter(sdk_binding=binding))

        with patch.dict(
            os.environ,
            {
                "X402_MODE": "real",
                "X402_NETWORK": "eip155:84532",
                "ORCHESTRATOR_PRIVATE_KEY": "0xBuyerKey",
                "ORCHESTRATOR_WALLET_ADDRESS": "0xBuyer",
                "HOTEL_AGENT_PAY_TO": "0xSeller",
            },
        ):
            response = service.run_payment_loop(real_demo_request())

        self.assertEqual(response.status, "mock_confirmed")
        self.assertEqual(response.payment.status, "settled")
        self.assertEqual(response.payment.tx_hash, "0xREALX402SETTLED")
        self.assertIsNone(response.payment_required)
        self.assertIn("No real hotel reservation was created", response.receipt.receipt_note)
        self.assertIn("real x402 settlement completed", response.audit_events[-2].message)
        self.assertEqual(binding.requirements_config["network"], "eip155:84532")
        self.assertEqual(binding.requirements_config["pay_to"], "0xSeller")
        self.assertEqual(binding.requirements_config["price"], "$0.01")

    def test_real_adapter_failure_returns_payment_failed_without_simulated_receipt(self):
        service = AgenticHotelPaymentService(
            payment_adapter=X402RealAdapter(sdk_binding=FakeX402Binding(fail_settlement=True))
        )

        with patch.dict(
            os.environ,
            {
                "X402_MODE": "real",
                "X402_NETWORK": "eip155:84532",
                "ORCHESTRATOR_PRIVATE_KEY": "0xBuyerKey",
                "ORCHESTRATOR_WALLET_ADDRESS": "0xBuyer",
                "HOTEL_AGENT_PAY_TO": "0xSeller",
            },
        ):
            response = service.run_payment_loop(real_demo_request())

        self.assertEqual(response.status, "payment_failed")
        self.assertIsNone(response.receipt)
        self.assertIsNone(response.payment)
        self.assertEqual(response.error.code, "x402_real_settlement_failed")
        self.assertEqual(response.audit_events[-1].type, "payment_failed")

    def test_hotel_booking_endpoint_runs_backend_smoke_path(self):
        response = TestClient(app).post(
            "/hotel-booking",
            json={
                "trip_id": "tc-demo-osaka-001",
                "idempotency_key": "tc-demo-osaka-001:demo",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "mock_confirmed")
        self.assertEqual(payload["payment"]["status"], "simulated")
        self.assertTrue(payload["receipt"]["booking_id"].startswith("TC-MOCK-HOTEL-"))
        self.assertIn("No real hotel reservation was created", payload["receipt"]["receipt_note"])
        self.assertEqual(
            [event["type"] for event in payload["audit_events"]],
            [
                "mandate_validated",
                "payment_required",
                "payment_completed",
                "booking_confirmed",
            ],
        )

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


if __name__ == "__main__":
    unittest.main()
