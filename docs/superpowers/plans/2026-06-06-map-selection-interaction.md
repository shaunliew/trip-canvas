# Map Selection Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task.

**Goal:** Make the TripCanvas Mapbox surface clearly respond when a user selects a recommended place, so the demo reads like an AI-native trip map rather than static pins.

**Design thesis:** A selected place should create three immediate signals: the marker becomes visually dominant, a compact map-attached callout explains the decision, and the active day route reads like the chosen navigation path. Keep the panels minimal and do not add another map engine or backend contract.

**References checked:**

- Mapbox GL JS clicked-feature and hover examples for layer interactions.
- Mapbox GL JS GeoJSON line examples for route lines, casing, dash styling, and animation patterns.
- Google Places UI Kit and Apple Maps guidance as product inspiration for compact selected-place callouts.

## File Structure

Create:

- `frontend/lib/trip/map-overlay.ts`: Pure helper for positioning a map-attached callout within viewport bounds.
- `frontend/lib/trip/map-overlay.test.mjs`: Node tests for callout placement and clamping behavior.

Modify:

- `frontend/components/map/TripMap.tsx`: Add selected-place callout state, stronger selected marker styling, route casing/dash layer, and optional reduced-motion-safe route dash animation.

Do not modify:

- Backend contracts or data files.
- `.env` files or token handling.
- Map provider, renderer, or dependency list.

## Task 1: Callout Position Helper

- [ ] Add failing tests for desktop, mobile, and edge clamping in `map-overlay.test.mjs`.
- [ ] Implement `getMapCalloutPosition` in `map-overlay.ts`.
- [ ] Run `npm run test:unit` and confirm the new tests pass.

## Task 2: Map-Attached Selected Place Callout

- [ ] In `TripMap.tsx`, track the projected screen position of `selectedPlace` using `map.project`.
- [ ] Recalculate the callout position on `move`, `zoom`, `resize`, and selected-place changes.
- [ ] Render a small React DOM callout above the selected marker with name, day/category, concise rationale, and evidence/travel-fit copy.
- [ ] Add `data-testid="selected-place-map-callout"` for browser verification.
- [ ] Keep the callout pointer-events disabled except for text readability; selection remains driven by the map and existing panels.

## Task 3: Stronger Selected Marker Feedback

- [ ] Increase selected marker radius, stroke contrast, and halo opacity.
- [ ] Dim non-selected markers more decisively while preserving surrounding context.
- [ ] Add a selected halo pulse using Mapbox paint-property updates, disabled for reduced-motion users.

## Task 4: Navigation-Like Active Route

- [ ] Add a route casing layer under all routes.
- [ ] Keep inactive routes visible but muted.
- [ ] Add an active route dash layer above the selected day route.
- [ ] Animate the dash pattern only when reduced motion is not requested.

## Task 5: Verification

- [ ] Run `npm run test:unit`.
- [ ] Run `npm run typecheck`.
- [ ] Run `npm run build`.
- [ ] Browser verify with backend cache data on a temporary non-3000/3001 port, leaving ports `3000` and `3001` free for the user.
- [ ] Confirm the selected callout appears, clicking a place changes it, route styling is visible, and mobile layout does not overlap core panels.
