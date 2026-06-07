# Codebase Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven development or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean and organize TripCanvas without changing the demo flow, backend API/SSE contracts, Mapbox frontend direction, or AP2/x402 payment behavior.

**Architecture:** Use the conservative cleanup path: make backend imports/package layout reliable first, then extract only the largest mixed-responsibility modules behind compatibility facades. Frontend cleanup should split pure helpers and presentational subcomponents out of oversized files while preserving the current UI and behavior.

**Tech Stack:** FastAPI, Pydantic, pytest, Next.js App Router, React 19, TypeScript, node:test, Mapbox GL JS.

---

## Summary

- Current backend baseline fails: `uv run pytest backend/tests -q` cannot import `backend.*` because `backend/` is not a package.
- Current frontend baseline passes with direct Node invocation: unit tests pass and `tsc --noEmit` passes.
- Keep all public contracts unchanged: `/health`, `/demo-cache`, `/extract`, `/hotel-base`, `/itinerary`, `/ap2/hotel-booking-mandate`, `/hotel-booking`, and SSE `result` then `[DONE]`.
- Do not touch or stage the existing dirty `backend/data/places.json`.

## Public Interface Changes

- Add package-qualified backend imports internally: `backend.main`, `backend.spike_planner`, `backend.spike_agentic_payments`.
- Keep legacy `backend/spike_*.py` modules as compatibility facades during this cleanup.
- No backend response schema, SSE event, env var, Mapbox token, or frontend route changes.
- Update docs only after code/tests are green, replacing the old "flat hackathon layout" note with the new organized layout.

## Task Sequence

### Task 1: Backend Import Hygiene

**Files:** create `backend/__init__.py`; modify `pyproject.toml`, `backend/main.py`, `backend/spike_e2e_planner.py`, `backend/spike_planner.py`, all `backend/tests/test_*.py`.

- [ ] Add `backend/tests/test_import_contract.py` proving `import backend.main`, `import backend.spike_planner`, and `import backend.spike_agentic_payments` work from repo root.
- [ ] Run `uv run pytest backend/tests/test_import_contract.py -q`; expected current failure is `ModuleNotFoundError: No module named 'backend'`.
- [ ] Add pytest config in `pyproject.toml`: `testpaths = ["backend/tests"]`, `pythonpath = ["."]`.
- [ ] Remove test-local `sys.path.insert(...)` hacks and standardize test imports on `backend.*`.
- [ ] Replace runtime sibling imports with package imports; remove `sys.path.insert` from `backend/main.py`.
- [ ] Run `uv run pytest backend/tests -q`.
- [ ] Commit: `chore: make backend imports package-safe`.

### Task 2: Thin FastAPI Entrypoint

**Files:** create `backend/api/__init__.py`, `backend/api/schemas.py`, `backend/api/streaming.py`; modify `backend/main.py`, `backend/tests/test_cache_contract.py`, `backend/tests/test_itinerary_stage_events.py`.

- [ ] Move request/response models from `backend/main.py` into `backend/api/schemas.py`.
- [ ] Move `_sse_event`, `_itinerary_stream`, `_hotel_base_stream`, `_cap_hotel_base_places`, heartbeat constants, and cache-load error handling into `backend/api/streaming.py`.
- [ ] Keep `backend/main.py` focused on app construction, CORS, route declarations, and service calls.
- [ ] Preserve temporary compatibility aliases in `backend/main.py` for `_itinerary_stream` and `run_planner` until tests are updated.
- [ ] Verify: `uv run pytest backend/tests/test_demo_cache_endpoint.py backend/tests/test_cache_contract.py backend/tests/test_itinerary_stage_events.py -q`.
- [ ] Commit: `refactor: split FastAPI schemas and streams`.

### Task 3: Backend Domain Extraction

**Files:** create `backend/payments/{__init__.py,models.py,hotel_tool.py,ap2.py,x402.py,service.py}` and `backend/planner/{__init__.py,models.py,hotel_options.py,prompts.py,runner.py}`; modify `backend/spike_agentic_payments.py`, `backend/spike_planner.py`.

- [ ] Split `spike_agentic_payments.py` by responsibility: Pydantic models/exceptions, hotel-tool loading, AP2 signing/verification, x402 adapters, and `AgenticHotelPaymentService`.
- [ ] Make `backend/spike_agentic_payments.py` re-export the same public and test-used private names, including `_sign_ap2_payload`.
- [ ] Split `spike_planner.py` into planner models, hotel-option helpers, prompt builders, and runner/validation code.
- [ ] Make `backend/spike_planner.py` re-export existing names used by backend and tests.
- [ ] Verify: `uv run pytest backend/tests/test_agentic_hotel_payments.py backend/tests/test_planner_hotel_base.py backend/tests/test_planner_stops.py -q`.
- [ ] Commit: `refactor: organize planner and payment domains`.

### Task 4: Frontend Shell Extraction

**Files:** create `frontend/lib/trip/generation-state.ts`, `frontend/lib/trip/generation-state.test.mjs`, `frontend/lib/trip/booking-flow.ts`, `frontend/lib/trip/booking-flow.test.mjs`, `frontend/components/trip/{ReelInputPanel,GenerationTimeline,AgentDecisionRail,PlanApprovalCard,BookingFlowPanel}.tsx`; modify `frontend/components/trip/TripGenerationShell.tsx`.

- [ ] Move pure helpers and constants out of `TripGenerationShell.tsx`: reel parsing, map mode selection, steering signal building, hotel preference signal building, booking labels, payment formatting, and stream event readers.
- [ ] Move local JSX subcomponents into focused component files listed above.
- [ ] Keep orchestration state and handler wiring in `TripGenerationShell.tsx`; do not redesign layout or copy.
- [ ] Add node:test coverage for extracted pure helpers.
- [ ] Verify: `cd frontend && npm run test:unit && npm run typecheck`.
- [ ] Commit: `refactor: split trip generation shell`.

### Task 5: Frontend Map Extraction

**Files:** create `frontend/lib/trip/map-feature-collections.ts`, `frontend/lib/trip/map-feature-collections.test.mjs`, `frontend/lib/trip/map-layers.ts`, `frontend/lib/trip/map-runtime.ts`; modify `frontend/components/map/TripMap.tsx`.

- [ ] Move GeoJSON feature builders and hotel-hub derivation into `map-feature-collections.ts`.
- [ ] Move Mapbox source/layer IDs and `ensure*Layers` functions into `map-layers.ts`.
- [ ] Move runtime guard, token redaction, and expected Mapbox-noise filtering into `map-runtime.ts`.
- [ ] Keep React effects, refs, camera movement, and interaction callbacks in `TripMap.tsx`.
- [ ] Add tests that compare route/place/hotel feature output for representative trips.
- [ ] Verify: `cd frontend && npm run test:unit && npm run typecheck && npm run build`.
- [ ] Commit: `refactor: organize TripMap internals`.

### Task 6: Docs And Final Validation

**Files:** modify `CLAUDE.md`, `README.md`; optionally create `docs/superpowers/plans/2026-06-07-codebase-cleanup.md` with this plan during execution.

- [ ] Update `CLAUDE.md` to describe the compatibility-facade layout and remove the stale instruction to leave `backend/lib` empty.
- [ ] Update README verification commands to run from repo root for backend and `frontend/` for frontend.
- [ ] Do not delete local ignored directories (`.venv`, `frontend/node_modules`, `frontend/.next`) unless the user separately approves local cleanup.
- [ ] Run final checks: `uv run pytest backend/tests -q`, `cd frontend && npm run test:unit`, `cd frontend && npm run typecheck`, `cd frontend && npm run build`, `git diff --check`, `git status --short`.
- [ ] Commit: `docs: document organized codebase layout`.

## Assumptions

- Cleanup depth is **Conservative**.
- `backend/data/places.json` is user-owned dirty state and must not be rewritten or staged.
- No frontend redesign, no new map/rendering libraries, no API contract changes, and no payment behavior changes.
- The plan is presented here because current Plan Mode forbids writing repo files; during execution it should be saved to `docs/superpowers/plans/2026-06-07-codebase-cleanup.md`.
