"""Simulation-first agentic hotel payments for TripCanvas.

This module keeps the AP2-shaped mandate and x402-shaped booking loop behind a
small service boundary. It does not perform network calls or real settlement.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


_DEFAULT_TRIP_ID = "tc-demo-osaka-001"
_DEFAULT_CHECKIN = date(2026, 6, 10)
_DEFAULT_CHECKOUT = date(2026, 6, 13)
_DEFAULT_NETWORK = "base-sepolia"
_DEFAULT_X402_NETWORK = "eip155:84532"
_DEFAULT_ASSET = "USDC"
_DEFAULT_AGENT_PAYMENT_USD = Decimal("0.01")
_DEFAULT_PAYER = "0xOrchestratorDemo"
_DEFAULT_PAYEE = "0xHotelAgentDemo"
_RECEIPT_NOTE = "Demo-safe mock booking. No real hotel reservation was created."


class AuditEvent(BaseModel):
    type: str
    message: str
    simulated: Optional[bool] = None


class BookingError(BaseModel):
    code: str
    message: str


class BookingMandate(BaseModel):
    mandate_id: str
    mode: str = "autonomous"
    allowed_action: str
    city: str
    checkin: date
    checkout: date
    guests: int = Field(ge=1)
    budget: str
    hotel_preferences: list[str] = Field(default_factory=list)
    max_total_sgd: int = Field(gt=0)
    max_agent_payment_usd: Decimal
    payment_protocol: Literal["x402"] = "x402"
    network: str = _DEFAULT_NETWORK
    expires_at: datetime
    requires_user_visible_receipt: bool = True
    mock_booking_only: bool = True


class HotelBookingRequest(BaseModel):
    trip_id: str = _DEFAULT_TRIP_ID
    hotel_base: Optional[dict[str, Any]] = None
    mandate: Optional[BookingMandate] = None
    idempotency_key: Optional[str] = None


class PaymentInstructions(BaseModel):
    protocol: Literal["x402"] = "x402"
    network: str
    asset: str
    amount: str
    payer: str
    payee: str
    hotel_id: str
    payment_request_id: str
    message: str
    simulated: bool = True


class PaymentProof(BaseModel):
    protocol: Literal["x402"] = "x402"
    network: str
    asset: str
    amount: str
    payer: str
    payee: str
    hotel_id: str
    payment_request_id: str
    idempotency_key: str
    tx_hash: str
    status: Literal["simulated", "signed"] = "simulated"
    simulated: bool = True
    x402_payload: Any = Field(default=None, exclude=True)
    x402_requirements: Any = Field(default=None, exclude=True)


class PaymentReceipt(BaseModel):
    protocol: Literal["x402"] = "x402"
    network: str
    asset: str
    amount: str
    payer: str
    payee: str
    tx_hash: str
    status: Literal["simulated", "settled"] = "simulated"


class HotelBookingReceipt(BaseModel):
    type: Literal["hotel_booking_receipt"] = "hotel_booking_receipt"
    booking_id: str
    status: Literal["mock_confirmed"] = "mock_confirmed"
    is_mock: bool = True
    hotel: dict[str, Any]
    stay: dict[str, Any]
    pricing: dict[str, Any]
    payment: PaymentReceipt
    mandate: dict[str, Any]
    receipt_note: str = _RECEIPT_NOTE


class HotelBookingResponse(BaseModel):
    status: Literal["payment_required", "mock_confirmed", "rejected", "payment_failed"]
    audit_events: list[AuditEvent] = Field(default_factory=list)
    payment_required: Optional[PaymentInstructions] = None
    payment: Optional[PaymentReceipt] = None
    receipt: Optional[HotelBookingReceipt] = None
    error: Optional[BookingError] = None


class PaymentAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, simulated: Optional[bool]):
        super().__init__(message)
        self.code = code
        self.message = message
        self.simulated = simulated


class PaymentSimulationError(PaymentAdapterError):
    def __init__(self, message: str = "x402 payment simulation failed."):
        super().__init__("payment_simulation_failed", message, True)


class X402RealPaymentError(PaymentAdapterError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, False)


class ConstraintViolation(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class BookingContext:
    hotel_base: dict[str, Any]
    selected_hotel: dict[str, Any]
    mandate: BookingMandate
    idempotency_key: str
    nights: int
    estimated_total_sgd: int
    agent_payment_usd: Decimal
    network: str
    asset: str
    payer: str
    payee: str


def _default_hotel_tool_path() -> Path:
    return Path(__file__).with_name("data") / "planner_output.json"


def load_hotel_tool_dict(path: Optional[str | Path] = None) -> dict[str, Any]:
    hotel_tool_path = Path(path) if path is not None else _default_hotel_tool_path()
    with hotel_tool_path.open(encoding="utf-8") as fh:
        loaded = json.load(fh)
    if not isinstance(loaded, dict):
        raise ConstraintViolation("invalid_hotel_tool", "Hotel tool payload must be a JSON object.")
    return loaded


def load_hotel_base_dict(path: Optional[str | Path] = None) -> dict[str, Any]:
    return load_hotel_tool_dict(path)


def resolve_selected_hotel(hotel_tool: dict[str, Any]) -> dict[str, Any]:
    hotel_options = hotel_tool.get("hotel_options")
    if isinstance(hotel_options, list):
        return _resolve_selected_hotel_option(hotel_tool, hotel_options)

    selected_hotel_id = hotel_tool.get("selected_hotel_id")
    candidates = hotel_tool.get("hotel_candidates")
    if not isinstance(selected_hotel_id, str) or not selected_hotel_id:
        raise ConstraintViolation("selected_hotel_not_found", "Hotel-base payload does not name a selected hotel.")
    if not isinstance(candidates, list):
        raise ConstraintViolation("selected_hotel_not_found", "Hotel-base payload has no hotel candidates.")
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate.get("id") == selected_hotel_id:
            return candidate
    raise ConstraintViolation("selected_hotel_not_found", f"Selected hotel {selected_hotel_id!r} was not found.")


def _resolve_selected_hotel_option(
    hotel_tool: dict[str, Any],
    hotel_options: list[Any],
) -> dict[str, Any]:
    selected_hotel_id = hotel_tool.get("selected_hotel_id")
    if isinstance(selected_hotel_id, str) and selected_hotel_id:
        for option in hotel_options:
            if isinstance(option, dict) and option.get("id") == selected_hotel_id:
                return _enrich_planner_hotel_option(hotel_tool, option)
        raise ConstraintViolation("selected_hotel_not_found", f"Selected hotel {selected_hotel_id!r} was not found.")

    best_options = [
        option for option in hotel_options
        if isinstance(option, dict) and option.get("is_best") is True
    ]
    if len(best_options) == 1:
        return _enrich_planner_hotel_option(hotel_tool, best_options[0])
    if len(best_options) > 1:
        raise ConstraintViolation("selected_hotel_not_found", "Planner output has multiple best hotel options.")

    recommended_hotel = str(hotel_tool.get("recommended_hotel") or "").strip()
    if recommended_hotel:
        for option in hotel_options:
            if not isinstance(option, dict):
                continue
            if option.get("id") == recommended_hotel or option.get("name") == recommended_hotel:
                return _enrich_planner_hotel_option(hotel_tool, option)

    raise ConstraintViolation("selected_hotel_not_found", "Planner output does not name a selected hotel option.")


def _enrich_planner_hotel_option(
    hotel_tool: dict[str, Any],
    hotel_option: dict[str, Any],
) -> dict[str, Any]:
    selected_hotel = dict(hotel_option)
    selected_hotel.setdefault("city", _tool_destination_city(hotel_tool))
    selected_hotel.setdefault("area", _hotel_area_name(selected_hotel))
    return selected_hotel


def _tool_destination_city(hotel_tool: dict[str, Any]) -> Optional[str]:
    weather_report = hotel_tool.get("weather_report")
    if isinstance(weather_report, dict):
        destination = weather_report.get("destination")
        if isinstance(destination, str) and destination.strip():
            return destination.strip()
    return None


def _hotel_area_name(hotel: dict[str, Any]) -> Optional[str]:
    base_area_id = hotel.get("base_area_id")
    if not isinstance(base_area_id, str) or not base_area_id.strip():
        return None
    clean = base_area_id.removeprefix("base_").replace("_", " ")
    return clean.title()


def build_default_demo_mandate(
    hotel_tool: dict[str, Any],
    trip_id: str = _DEFAULT_TRIP_ID,
) -> BookingMandate:
    selected_hotel = resolve_selected_hotel(hotel_tool)
    payment_context = _payment_context(hotel_tool)
    price_per_night = selected_hotel.get("price_per_night_sgd")
    if isinstance(price_per_night, int):
        max_total_sgd = max(price_per_night * 3 + 50, 650)
    else:
        max_total_sgd = 650
    mandate_id = f"ap2-demo-{trip_id}"
    return BookingMandate(
        mandate_id=mandate_id,
        mode="autonomous",
        allowed_action="mock_hotel_booking",
        city=str(selected_hotel.get("city") or _tool_destination_city(hotel_tool) or "Tokyo"),
        checkin=_DEFAULT_CHECKIN,
        checkout=_DEFAULT_CHECKOUT,
        guests=2,
        budget=str(selected_hotel.get("budget_tier") or "mid_range"),
        hotel_preferences=["near_station", "quiet", "near_convenience_store"],
        max_total_sgd=max_total_sgd,
        max_agent_payment_usd=_decimal_str(payment_context["agent_payment_usd"]),
        payment_protocol="x402",
        network=str(payment_context["network"]),
        expires_at=datetime(2030, 6, 10, tzinfo=timezone.utc),
        requires_user_visible_receipt=True,
        mock_booking_only=True,
    )


def deterministic_booking_id(
    trip_id: str,
    mandate_id: str,
    hotel_id: str,
    checkin: date,
    checkout: date,
    guests: int,
) -> str:
    digest = hashlib.sha1(
        f"{trip_id}|{mandate_id}|{hotel_id}|{checkin.isoformat()}|{checkout.isoformat()}|{guests}".encode()
    ).hexdigest()
    return f"TC-MOCK-HOTEL-{digest[:8].upper()}"


class X402SimulationAdapter:
    def __init__(self, simulate_failure: bool = False):
        self.simulate_failure = simulate_failure

    def create_payment_proof(
        self,
        request: HotelBookingRequest,
        instructions: PaymentInstructions,
    ) -> PaymentProof:
        if self.simulate_failure:
            raise PaymentSimulationError("x402 payment simulation failed")
        idempotency_key = _require_idempotency_key(request)
        tx_material = "|".join(
            [
                idempotency_key,
                request.trip_id,
                request.mandate.mandate_id if request.mandate else "",
                instructions.hotel_id,
                instructions.amount,
                instructions.network,
                instructions.payment_request_id,
            ]
        )
        tx_hash = "0xSIMULATED" + hashlib.sha1(tx_material.encode()).hexdigest().upper()[:24]
        return PaymentProof(
            network=instructions.network,
            asset=instructions.asset,
            amount=instructions.amount,
            payer=instructions.payer,
            payee=instructions.payee,
            hotel_id=instructions.hotel_id,
            payment_request_id=instructions.payment_request_id,
            idempotency_key=idempotency_key,
            tx_hash=tx_hash,
        )

    def validate_payment_proof(
        self,
        proof: PaymentProof,
        instructions: PaymentInstructions,
        idempotency_key: str,
    ) -> PaymentReceipt:
        expected_fields = {
            "network": instructions.network,
            "asset": instructions.asset,
            "amount": instructions.amount,
            "payer": instructions.payer,
            "payee": instructions.payee,
            "hotel_id": instructions.hotel_id,
            "payment_request_id": instructions.payment_request_id,
            "idempotency_key": idempotency_key,
        }
        for field_name, expected in expected_fields.items():
            if getattr(proof, field_name) != expected:
                raise ConstraintViolation(
                    "payment_proof_mismatch",
                    f"Payment proof {field_name} does not match the payment request.",
                )
        if not proof.tx_hash.startswith("0xSIMULATED"):
            raise ConstraintViolation("payment_proof_mismatch", "Payment proof is not a simulated x402 tx.")
        return PaymentReceipt(
            network=proof.network,
            asset=proof.asset,
            amount=proof.amount,
            payer=proof.payer,
            payee=proof.payee,
            tx_hash=proof.tx_hash,
        )


class X402SdkBinding:
    def __init__(
        self,
        *,
        private_key: str,
        facilitator_url: str,
        network: str,
    ):
        try:
            from eth_account import Account
            from x402 import ResourceConfig, x402ClientSync, x402ResourceServerSync
            from x402.http import FacilitatorConfig, HTTPFacilitatorClientSync
            from x402.mechanisms.evm import EthAccountSigner
            from x402.mechanisms.evm.exact import ExactEvmServerScheme
            from x402.mechanisms.evm.exact.register import register_exact_evm_client
            from x402.schemas.payments import ResourceInfo
        except ImportError as exc:
            raise X402RealPaymentError(
                "x402_sdk_unavailable",
                "x402 SDK is not installed with the required httpx and evm extras.",
            ) from exc

        try:
            account = Account.from_key(private_key)
            facilitator = HTTPFacilitatorClientSync(FacilitatorConfig(url=facilitator_url))
            self.server = x402ResourceServerSync(facilitator)
            self.server.register(network, ExactEvmServerScheme())
            self.server.initialize()

            self.client = x402ClientSync()
            register_exact_evm_client(
                self.client,
                EthAccountSigner(account),
                networks=network,
            )
        except Exception as exc:
            raise X402RealPaymentError(
                "x402_real_client_init_failed",
                f"x402 real client initialization failed: {type(exc).__name__}.",
            ) from exc

        self._resource_config_cls = ResourceConfig
        self._resource_info_cls = ResourceInfo

    def build_payment_requirements(
        self,
        *,
        network: str,
        pay_to: str,
        price: str,
        resource_url: str,
        description: str,
    ) -> tuple[list[Any], Any]:
        resource_config = self._resource_config_cls(
            scheme="exact",
            network=network,
            payTo=pay_to,
            price=price,
        )
        resource = self._resource_info_cls(
            url=resource_url,
            description=description,
            mimeType="application/json",
            serviceName="TripCanvas Hotel Booking Agent",
            tags=["tripcanvas", "hotel-booking", "x402"],
        )
        return self.server.build_payment_requirements(resource_config), resource

    def create_payment_payload(self, requirements_and_resource: tuple[list[Any], Any]) -> Any:
        requirements, resource = requirements_and_resource
        payment_required = self.server.create_payment_required_response(
            requirements,
            resource=resource,
        )
        return self.client.create_payment_payload(payment_required, resource=resource)

    def verify_and_settle(self, payload: Any, requirements_and_resource: tuple[list[Any], Any]) -> Any:
        requirements, _ = requirements_and_resource
        selected_requirements = requirements[0]
        verified = self.server.verify_payment(payload, selected_requirements)
        verify_result = getattr(verified, "verify", verified)
        if not _object_bool(verify_result, "is_valid", "isValid"):
            reason = _object_str(
                verify_result,
                "invalid_reason",
                "invalidReason",
                "invalid_message",
                "invalidMessage",
            )
            raise X402RealPaymentError(
                "x402_real_verification_failed",
                reason or "x402 facilitator rejected the payment proof.",
            )
        return self.server.settle_payment(payload, selected_requirements)


class X402RealAdapter:
    def __init__(self, sdk_binding: Optional[Any] = None):
        self._sdk_binding = sdk_binding

    def create_payment_proof(
        self,
        request: HotelBookingRequest,
        instructions: PaymentInstructions,
    ) -> PaymentProof:
        idempotency_key = _require_idempotency_key(request)
        config = _real_x402_config()
        try:
            binding = self._binding(config)
            requirements = binding.build_payment_requirements(
                network=config["network"],
                pay_to=config["payee"],
                price=f"${instructions.amount}",
                resource_url=f"tripcanvas://hotel-booking/{instructions.hotel_id}",
                description=f"TripCanvas mock hotel booking fee for {instructions.hotel_id}",
            )
            payload = binding.create_payment_payload(requirements)
        except X402RealPaymentError:
            raise
        except Exception as exc:
            raise X402RealPaymentError(
                "x402_real_payment_creation_failed",
                f"x402 payment payload creation failed: {type(exc).__name__}.",
            ) from exc

        return PaymentProof(
            network=config["network"],
            asset=instructions.asset,
            amount=instructions.amount,
            payer=config["payer"],
            payee=config["payee"],
            hotel_id=instructions.hotel_id,
            payment_request_id=instructions.payment_request_id,
            idempotency_key=idempotency_key,
            tx_hash="x402-signed-pending-settlement",
            status="signed",
            simulated=False,
            x402_payload=payload,
            x402_requirements=requirements,
        )

    def validate_payment_proof(
        self,
        proof: PaymentProof,
        instructions: PaymentInstructions,
        idempotency_key: str,
    ) -> PaymentReceipt:
        config = _real_x402_config()
        expected_fields = {
            "network": config["network"],
            "asset": instructions.asset,
            "amount": instructions.amount,
            "payer": config["payer"],
            "payee": config["payee"],
            "hotel_id": instructions.hotel_id,
            "payment_request_id": instructions.payment_request_id,
            "idempotency_key": idempotency_key,
        }
        for field_name, expected in expected_fields.items():
            if getattr(proof, field_name) != expected:
                raise X402RealPaymentError(
                    "x402_payment_proof_mismatch",
                    f"x402 payment proof {field_name} does not match the payment request.",
                )
        if proof.x402_payload is None or proof.x402_requirements is None:
            raise X402RealPaymentError(
                "x402_payment_proof_mismatch",
                "x402 payment proof is missing the signed payload or requirements.",
            )

        try:
            settlement = self._binding(config).verify_and_settle(
                proof.x402_payload,
                proof.x402_requirements,
            )
        except X402RealPaymentError:
            raise
        except Exception as exc:
            raise X402RealPaymentError(
                "x402_real_settlement_failed",
                f"x402 settlement failed: {type(exc).__name__}.",
            ) from exc

        if not _settlement_success(settlement):
            reason = _settlement_error(settlement) or "x402 settlement was not successful."
            raise X402RealPaymentError("x402_real_settlement_failed", reason)

        tx_hash = _settlement_transaction(settlement)
        if not tx_hash:
            raise X402RealPaymentError(
                "x402_real_settlement_failed",
                "x402 settlement succeeded without a transaction reference.",
            )

        return PaymentReceipt(
            network=proof.network,
            asset=proof.asset,
            amount=proof.amount,
            payer=proof.payer,
            payee=proof.payee,
            tx_hash=tx_hash,
            status="settled",
        )

    def _binding(self, config: dict[str, str]) -> Any:
        if self._sdk_binding is None:
            self._sdk_binding = X402SdkBinding(
                private_key=config["private_key"],
                facilitator_url=config["facilitator_url"],
                network=config["network"],
            )
        return self._sdk_binding


def build_x402_payment_adapter() -> Any:
    if _x402_mode() == "real":
        return X402RealAdapter()
    return X402SimulationAdapter()


class AgenticHotelPaymentService:
    def __init__(self, payment_adapter: Optional[Any] = None):
        self.payment_adapter = payment_adapter or build_x402_payment_adapter()

    def attempt_booking(
        self,
        request: HotelBookingRequest | dict[str, Any],
        payment_proof: Optional[PaymentProof] = None,
    ) -> HotelBookingResponse:
        try:
            normalized = self._normalize_request(request)
            context = self._build_context(normalized)
        except ConstraintViolation as exc:
            return _rejected(exc)

        instructions = _payment_instructions(context)
        if payment_proof is None:
            return HotelBookingResponse(
                status="payment_required",
                audit_events=[
                    AuditEvent(
                        type="mandate_validated",
                        message=(
                            "Mandate allows mock hotel booking within "
                            f"SGD {context.mandate.max_total_sgd}."
                        ),
                    ),
                    AuditEvent(
                        type="payment_required",
                        message=f"Hotel booking agent requires {instructions.amount} testnet {instructions.asset}.",
                    ),
                ],
                payment_required=instructions,
            )

        try:
            payment = self.payment_adapter.validate_payment_proof(
                payment_proof,
                instructions,
                context.idempotency_key,
            )
            receipt = _booking_receipt(normalized, context, payment)
        except PaymentAdapterError as exc:
            return _payment_failed(
                [
                    AuditEvent(
                        type="mandate_validated",
                        message=(
                            "Mandate allows mock hotel booking within "
                            f"SGD {context.mandate.max_total_sgd}."
                        ),
                    )
                ],
                exc,
            )
        except ConstraintViolation as exc:
            return _rejected(exc)

        return HotelBookingResponse(
            status="mock_confirmed",
            audit_events=[
                AuditEvent(
                    type="mandate_validated",
                    message=(
                        "Mandate allows mock hotel booking within "
                        f"SGD {context.mandate.max_total_sgd}."
                    ),
                ),
                AuditEvent(type="booking_confirmed", message="Mock hotel booking receipt issued."),
            ],
            payment=payment,
            receipt=receipt,
        )

    def run_payment_loop(
        self,
        request: HotelBookingRequest | dict[str, Any],
    ) -> HotelBookingResponse:
        first_attempt = self.attempt_booking(request)
        if first_attempt.status != "payment_required" or first_attempt.payment_required is None:
            return first_attempt

        try:
            normalized = self._normalize_request(request)
            proof = self.payment_adapter.create_payment_proof(normalized, first_attempt.payment_required)
        except PaymentAdapterError as exc:
            return _payment_failed(first_attempt.audit_events, exc)
        except ConstraintViolation as exc:
            return _rejected(exc)

        retry = self.attempt_booking(normalized, payment_proof=proof)
        if retry.status == "payment_failed":
            failed_events = [
                event for event in retry.audit_events
                if event.type != "mandate_validated"
            ]
            return retry.model_copy(
                update={"audit_events": [*first_attempt.audit_events, *failed_events]}
            )
        if retry.status != "mock_confirmed":
            return retry
        payment_completed = _payment_completed_event(retry.payment)
        return retry.model_copy(
            update={
                "audit_events": [
                    *first_attempt.audit_events,
                    payment_completed,
                    AuditEvent(type="booking_confirmed", message="Mock hotel booking receipt issued."),
                ]
            }
        )

    def _normalize_request(
        self,
        request: HotelBookingRequest | dict[str, Any],
    ) -> HotelBookingRequest:
        normalized = (
            request
            if isinstance(request, HotelBookingRequest)
            else HotelBookingRequest.model_validate(request)
        )
        hotel_base = normalized.hotel_base or load_hotel_tool_dict()
        mandate = normalized.mandate or build_default_demo_mandate(hotel_base, normalized.trip_id)
        idempotency_key = normalized.idempotency_key
        if not idempotency_key:
            selected_hotel = resolve_selected_hotel(hotel_base)
            idempotency_key = f"{normalized.trip_id}:{mandate.mandate_id}:{selected_hotel['id']}"
        return normalized.model_copy(
            update={
                "hotel_base": hotel_base,
                "mandate": mandate,
                "idempotency_key": idempotency_key,
            }
        )

    def _build_context(self, request: HotelBookingRequest) -> BookingContext:
        _validate_environment()
        if request.hotel_base is None or request.mandate is None:
            raise ConstraintViolation("invalid_booking_request", "Booking request was not normalized.")

        selected_hotel = resolve_selected_hotel(request.hotel_base)
        mandate = request.mandate
        _validate_mandate(mandate)
        nights = (mandate.checkout - mandate.checkin).days
        if nights <= 0:
            raise ConstraintViolation("invalid_stay_dates", "Checkout must be after check-in.")

        if str(selected_hotel.get("city") or mandate.city) != mandate.city:
            raise ConstraintViolation("city_constraint_mismatch", "Selected hotel city violates the mandate.")
        if selected_hotel.get("budget_tier") and selected_hotel.get("budget_tier") != mandate.budget:
            raise ConstraintViolation("budget_constraint_mismatch", "Selected hotel budget tier violates the mandate.")

        price_per_night = selected_hotel.get("price_per_night_sgd")
        if not isinstance(price_per_night, int):
            raise ConstraintViolation(
                "selected_hotel_missing_price",
                "Selected hotel lacks price_per_night_sgd.",
            )
        rooms = selected_hotel.get("mock_available_rooms")
        if not isinstance(rooms, int) or rooms <= 0:
            raise ConstraintViolation("no_mock_rooms_available", "Selected hotel has no mock rooms available.")

        estimated_total_sgd = price_per_night * nights
        if estimated_total_sgd > mandate.max_total_sgd:
            raise ConstraintViolation(
                "stay_total_exceeds_mandate",
                f"Estimated stay total SGD {estimated_total_sgd} exceeds the mandate.",
            )

        payment_context = _payment_context(request.hotel_base)
        agent_payment_usd = _decimal(payment_context["agent_payment_usd"])
        if agent_payment_usd > mandate.max_agent_payment_usd:
            raise ConstraintViolation(
                "agent_payment_exceeds_mandate",
                "Agent payment amount exceeds the mandate.",
            )
        if str(payment_context["network"]) != mandate.network:
            raise ConstraintViolation("payment_network_mismatch", "Payment network violates the mandate.")
        if str(payment_context["payment_protocol"]) != mandate.payment_protocol:
            raise ConstraintViolation("payment_protocol_mismatch", "Payment protocol violates the mandate.")
        if payment_context.get("mock_booking_only") is not True:
            raise ConstraintViolation("mock_booking_required", "Hotel payment context must be mock-only.")

        return BookingContext(
            hotel_base=request.hotel_base,
            selected_hotel=selected_hotel,
            mandate=mandate,
            idempotency_key=_require_idempotency_key(request),
            nights=nights,
            estimated_total_sgd=estimated_total_sgd,
            agent_payment_usd=agent_payment_usd,
            network=str(payment_context["network"]),
            asset=str(payment_context["asset"]),
            payer=os.getenv("ORCHESTRATOR_WALLET_ADDRESS", _DEFAULT_PAYER),
            payee=os.getenv("HOTEL_AGENT_PAY_TO", _DEFAULT_PAYEE),
        )


def _validate_environment() -> None:
    booking_mode = os.getenv("HOTEL_BOOKING_MODE")
    if booking_mode and booking_mode != "mock":
        raise ConstraintViolation(
            "hotel_booking_mode_not_mock",
            "HOTEL_BOOKING_MODE must be unset or 'mock' for demo booking.",
        )
    x402_mode = _x402_mode()
    if x402_mode not in {"simulation", "real"}:
        raise ConstraintViolation(
            "x402_mode_not_supported",
            "X402_MODE must be 'simulation' or 'real'.",
        )


def _validate_mandate(mandate: BookingMandate) -> None:
    if mandate.allowed_action != "mock_hotel_booking":
        raise ConstraintViolation(
            "mandate_action_not_allowed",
            "Mandate action must be mock_hotel_booking.",
        )
    if mandate.mock_booking_only is not True:
        raise ConstraintViolation("mock_booking_required", "Mandate must be mock-booking-only.")
    expires_at = mandate.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        raise ConstraintViolation("mandate_expired", "Mandate is expired.")
    if mandate.payment_protocol != "x402":
        raise ConstraintViolation("payment_protocol_mismatch", "Mandate must use x402.")


def _payment_context(hotel_base: dict[str, Any]) -> dict[str, Any]:
    raw = hotel_base.get("payment_context")
    context = raw if isinstance(raw, dict) else {}
    if _x402_mode() == "real":
        network = os.getenv("X402_NETWORK", _DEFAULT_X402_NETWORK)
    else:
        network = context.get("network", os.getenv("X402_NETWORK", _DEFAULT_NETWORK))
    return {
        "payment_protocol": context.get("payment_protocol", "x402"),
        "network": network,
        "asset": context.get("asset", _DEFAULT_ASSET),
        "agent_payment_usd": context.get(
            "agent_payment_usd",
            os.getenv("X402_HOTEL_BOOKING_PRICE_USD", str(_DEFAULT_AGENT_PAYMENT_USD)),
        ),
        "mock_booking_only": context.get("mock_booking_only", True),
    }


def _payment_instructions(context: BookingContext) -> PaymentInstructions:
    amount = _decimal_str(context.agent_payment_usd)
    request_material = "|".join(
        [
            context.idempotency_key,
            context.mandate.mandate_id,
            str(context.selected_hotel["id"]),
            amount,
            context.network,
        ]
    )
    payment_request_id = "x402_mock_" + hashlib.sha1(request_material.encode()).hexdigest()[:12]
    return PaymentInstructions(
        network=context.network,
        asset=context.asset,
        amount=amount,
        payer=context.payer,
        payee=context.payee,
        hotel_id=str(context.selected_hotel["id"]),
        payment_request_id=payment_request_id,
        message=f"Hotel booking agent requires {amount} testnet {context.asset}.",
        simulated=_x402_mode() == "simulation",
    )


def _booking_receipt(
    request: HotelBookingRequest,
    context: BookingContext,
    payment: PaymentReceipt,
) -> HotelBookingReceipt:
    hotel = context.selected_hotel
    booking_id = deterministic_booking_id(
        request.trip_id,
        context.mandate.mandate_id,
        str(hotel["id"]),
        context.mandate.checkin,
        context.mandate.checkout,
        context.mandate.guests,
    )
    return HotelBookingReceipt(
        booking_id=booking_id,
        hotel={
            "id": hotel.get("id"),
            "name": hotel.get("name"),
            "area": hotel.get("area"),
            "city": hotel.get("city") or context.mandate.city,
            "lat": hotel.get("lat"),
            "lng": hotel.get("lng"),
            "room_type": hotel.get("room_type"),
            "cancellation_policy": hotel.get("cancellation_policy"),
        },
        stay={
            "checkin": context.mandate.checkin.isoformat(),
            "checkout": context.mandate.checkout.isoformat(),
            "nights": context.nights,
            "guests": context.mandate.guests,
        },
        pricing={
            "price_per_night_sgd": hotel.get("price_per_night_sgd"),
            "estimated_total_sgd": context.estimated_total_sgd,
            "agent_payment_usd": _decimal_str(context.agent_payment_usd),
        },
        payment=payment,
        mandate={
            "mandate_id": context.mandate.mandate_id,
            "allowed_action": context.mandate.allowed_action,
            "mock_booking_only": context.mandate.mock_booking_only,
        },
        receipt_note=_receipt_note(payment),
    )


def _rejected(exc: ConstraintViolation) -> HotelBookingResponse:
    return HotelBookingResponse(
        status="rejected",
        audit_events=[
            AuditEvent(
                type="booking_rejected",
                message=exc.message,
            )
        ],
        error=BookingError(code=exc.code, message=exc.message),
    )


def _payment_failed(
    prior_events: list[AuditEvent],
    exc: PaymentAdapterError,
) -> HotelBookingResponse:
    return HotelBookingResponse(
        status="payment_failed",
        audit_events=[
            *prior_events,
            AuditEvent(
                type="payment_failed",
                message=exc.message,
                simulated=exc.simulated,
            ),
        ],
        error=BookingError(code=exc.code, message=exc.message),
    )


def _payment_completed_event(payment: Optional[PaymentReceipt]) -> AuditEvent:
    if payment is not None and payment.status == "settled":
        return AuditEvent(
            type="payment_completed",
            message="real x402 settlement completed.",
            simulated=False,
        )
    return AuditEvent(
        type="payment_completed",
        message="x402 payment simulation completed.",
        simulated=True,
    )


def _receipt_note(payment: PaymentReceipt) -> str:
    if payment.status == "settled":
        return (
            "Demo-safe mock booking. No real hotel reservation was created. "
            "The x402 payment may move testnet funds."
        )
    return _RECEIPT_NOTE


def _require_idempotency_key(request: HotelBookingRequest) -> str:
    if request.idempotency_key is None:
        raise ConstraintViolation("missing_idempotency_key", "Booking request lacks an idempotency key.")
    return request.idempotency_key


def _x402_mode() -> str:
    return os.getenv("X402_MODE", "simulation").strip().lower()


def _real_x402_config() -> dict[str, str]:
    private_key = os.getenv("ORCHESTRATOR_PRIVATE_KEY")
    payer = os.getenv("ORCHESTRATOR_WALLET_ADDRESS")
    payee = os.getenv("HOTEL_AGENT_PAY_TO")
    missing = [
        name for name, value in [
            ("ORCHESTRATOR_PRIVATE_KEY", private_key),
            ("ORCHESTRATOR_WALLET_ADDRESS", payer),
            ("HOTEL_AGENT_PAY_TO", payee),
        ]
        if not value
    ]
    if missing:
        raise X402RealPaymentError(
            "x402_real_config_missing",
            f"Real x402 mode is missing required env: {', '.join(missing)}.",
        )
    return {
        "private_key": str(private_key),
        "payer": str(payer),
        "payee": str(payee),
        "network": os.getenv("X402_NETWORK", _DEFAULT_X402_NETWORK),
        "facilitator_url": os.getenv("X402_FACILITATOR_URL", "https://x402.org/facilitator"),
    }


def _settlement_success(settlement: Any) -> bool:
    return _object_bool(settlement, "success")


def _settlement_transaction(settlement: Any) -> Optional[str]:
    value = _object_str(
        settlement,
        "transaction",
        "tx_hash",
        "txHash",
        "transaction_hash",
        "transactionHash",
        "hash",
    )
    return value if value and value != "None" else None


def _settlement_error(settlement: Any) -> Optional[str]:
    return _object_str(
        settlement,
        "error_reason",
        "errorReason",
        "error_message",
        "errorMessage",
        "error",
    )


def _object_bool(value: Any, *names: str) -> bool:
    for name in names:
        field = _object_value(value, name)
        if isinstance(field, bool):
            return field
    return False


def _object_str(value: Any, *names: str) -> Optional[str]:
    for name in names:
        field = _object_value(value, name)
        if field is not None:
            return str(field)
    return None


def _object_value(value: Any, name: str) -> Any:
    if isinstance(value, dict) and name in value:
        return value[name]
    return getattr(value, name, None)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _decimal_str(value: Any) -> str:
    return format(_decimal(value), "f")
