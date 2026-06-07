# Superpowers Planning Archive

This directory stores historical specs and implementation plans created during the TripCanvas sprint.

Use these files for execution history and rationale, not as the primary current-state docs. Some older files describe now-stale assumptions, including the previous flat backend layout, missing AP2 UI, or future-tense Mapbox frontend work.

Current source-of-truth docs:

- `../../README.md`
- `../../AGENTS.md`
- `../../CLAUDE.md`
- `../README.md`

Current repo shape to prefer when reading older plans:

- `backend/api/` owns FastAPI schemas and streaming helpers.
- `backend/planner/` owns planner implementation; `backend/spike_planner.py` is a compatibility facade.
- `backend/payments/` owns AP2/x402 hotel-payment implementation; `backend/spike_agentic_payments.py` is a compatibility facade.
- `frontend/components/trip/` and `frontend/lib/trip/` contain the implemented Mapbox generation shell, extracted-place UI, route helpers, and booking flow helpers.
