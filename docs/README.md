# TripCanvas Docs

This folder keeps planning history and reference notes out of the repo root.

## Source Of Truth

- `../README.md` - product overview, local run commands, implemented frontend/backend state, and verification commands.
- `../AGENTS.md` - agent-facing repo rules and TripCanvas product constraints.
- `../CLAUDE.md` - detailed backend contracts, SSE termination contract, env vars, package layout, and demo guardrails.

## Reference

- `reference/agentic-payments.md` - AP2-style authorization plus x402 hotel-payment reference for the current payment flow.

## Historical Plans And Specs

- `superpowers/specs/` - design specs written before or during implementation.
- `superpowers/plans/` - implementation plans and execution handoffs.

These historical files may mention older implementation assumptions such as the prior flat backend layout. When they conflict with current repo files or the source-of-truth docs above, treat the current repo and source-of-truth docs as authoritative.

## Current Verified Repo Shape

- Backend package imports are rooted at `backend.*`.
- FastAPI schemas and stream helpers live in `backend/api/`.
- Planner implementation lives in `backend/planner/`, with `backend/spike_planner.py` kept as a compatibility facade.
- AP2/x402 hotel-payment implementation lives in `backend/payments/`, with `backend/spike_agentic_payments.py` kept as a compatibility facade.
- The Next.js frontend lives in `frontend/`, with trip shell helpers under `frontend/lib/trip/` and presentational trip components under `frontend/components/trip/`.
- Mapbox layer/runtime/feature helpers live under `frontend/lib/trip/`, while `frontend/components/map/TripMap.tsx` owns React effects, camera movement, refs, and interactions.
