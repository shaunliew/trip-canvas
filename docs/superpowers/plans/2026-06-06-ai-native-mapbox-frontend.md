# AI-Native Mapbox Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revamp the TripCanvas frontend into a minimal AI-native Mapbox travel planning demo that makes agent decisions, evidence, selected locations, routes, and booking handoff clear.

**Architecture:** Keep the existing Next.js App Router frontend and Mapbox GL JS map. Add small pure helper functions for agent-facing copy, adjust existing components in place, and update Mapbox GeoJSON styling to dim non-selected places while emphasizing the selected stop and route. Do not touch backend contracts or add new dependencies.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind v4, Mapbox GL JS 3.24.0, Node test runner for pure helper tests.

---

## File Structure

Create:

- `frontend/lib/trip/agent-copy.ts`: Pure copy/summary helpers for selected-place rationale, evidence, tradeoffs, next action, and stage labels.
- `frontend/lib/trip/agent-copy.test.mjs`: Node tests that transpile and exercise `agent-copy.ts`.

Modify:

- `frontend/package.json`: Add a `test:unit` script for local pure helper tests.
- `frontend/components/map/TripMap.tsx`: Add selected-place dimming, selected-day route emphasis, and slightly quieter map chrome.
- `frontend/components/trip/TripGenerationShell.tsx`: Remove the click-through landing gate, use the new helper functions, sharpen the stage timeline, and add a final approval/payment placeholder.
- `frontend/components/trip/TripCanvasShell.tsx`: Pass selected-place route context into the map without changing backend data.
- `frontend/components/trip/LeftTripPanel.tsx`: Reduce visual density and foreground destination, days, hotel base, and filters.
- `frontend/components/trip/RightTripPanel.tsx`: Rename tabs around AI-native language and keep the agent panel central.
- `frontend/components/trip/PlaceIntelPanel.tsx`: Reframe selected-place details as "why chosen", "what to do", "evidence", and "travel fit".
- `frontend/components/trip/SelectedPlaceCard.tsx`: Make the floating selected-place card a concise rationale card.
- `frontend/app/globals.css`: Remove unused landing emphasis from the first-screen flow and tune scrollbars/panel utility styles if needed.

Do not modify:

- Backend files.
- `frontend/package-lock.json` unless npm writes it as part of a dependency change; no dependency change is planned.
- Mapbox token files or any `.env` file.

## Task 1: Agent Copy Helpers

**Files:**

- Create: `frontend/lib/trip/agent-copy.ts`
- Create: `frontend/lib/trip/agent-copy.test.mjs`
- Modify: `frontend/package.json`

- [ ] **Step 1: Write the failing tests**

Create `frontend/lib/trip/agent-copy.test.mjs` with tests for selected-place summaries, evidence fallback, tradeoff extraction, and stage labels:

```js
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function importAgentCopyModule() {
  const source = await readFile(new URL("./agent-copy.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(transpiled).toString("base64");

  return import(`data:text/javascript;base64,${encoded}`);
}

const agentCopy = await importAgentCopyModule();

const place = {
  id: "namba",
  name: "Namba",
  category: "market",
  day: 2,
  lat: 34.667,
  lng: 135.5,
  summary: "A food-heavy area with late-night streets.",
  evidenceQuote: "Namba street food",
  plannerSummary: "Chosen as a high-signal food stop near the hotel base.",
  dayPlanText: "Visit Namba in the evening after a short subway transfer.",
  confidence: 0.86,
};

test("buildSelectedPlaceDecision names the active stop and day", () => {
  assert.equal(
    agentCopy.buildSelectedPlaceDecision(place),
    "Namba is active on Day 2 because the planner found it useful for the mapped route.",
  );
});

test("buildEvidenceSummary prefers Reel evidence", () => {
  assert.equal(
    agentCopy.buildEvidenceSummary(place, { count: 1, source: "live" }),
    'Reel evidence: "Namba street food"',
  );
});

test("buildTradeoffSummary extracts route language from day text", () => {
  assert.equal(
    agentCopy.buildTradeoffSummary(place, {
      day: 2,
      title: "Food night",
      summary: "A compact route with one subway transfer.",
      placeIds: ["namba"],
    }),
    "Visit Namba in the evening after a short subway transfer.",
  );
});

test("getStageSteps marks planning active", () => {
  const steps = agentCopy.getStageSteps("planning_itinerary", true);
  assert.equal(steps.find((step) => step.key === "plan")?.active, true);
  assert.equal(steps.find((step) => step.key === "base")?.done, true);
});
```

- [ ] **Step 2: Add the unit-test script**

Modify `frontend/package.json` scripts to include:

```json
"test:unit": "node --test lib/trip/*.test.mjs"
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
npm run test:unit
```

Expected: fail because `agent-copy.ts` does not exist.

- [ ] **Step 4: Implement the helper**

Create `frontend/lib/trip/agent-copy.ts` with exported functions:

```ts
import type { ExtractResponse } from "@/lib/trip/backend-types";
import type { TripDay, TripHotelBase, TripPlace } from "@/lib/trip/types";

export type GenerationStatusForCopy =
  | "idle_globe"
  | "extracting_places"
  | "zooming_to_destination"
  | "choosing_hotel_base"
  | "optimizing_hotel_base"
  | "planning_itinerary"
  | "trip_ready"
  | "error";

export type StageStep = {
  key: "extract" | "ground" | "base" | "plan" | "approve";
  label: string;
  detail: string;
  active: boolean;
  done: boolean;
};
```

Also implement `getStageSteps`, `getAgentPanelTitle`, `buildSelectedPlaceDecision`, `buildEvidenceSummary`, `buildTradeoffSummary`, `buildNextActionSummary`, `formatPriorityTheme`, and local `truncateText`/`splitSentences` helpers.

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
npm run test:unit
```

Expected: all tests pass.

## Task 2: Map Focus And Route Emphasis

**Files:**

- Modify: `frontend/components/map/TripMap.tsx`
- Modify: `frontend/components/trip/TripCanvasShell.tsx`

- [ ] **Step 1: Extend map feature properties**

In `TripMap.tsx`, add `muted: boolean` to `PlaceFeatureProperties` and pass the selected place day into `buildRouteFeatureCollection`.

- [ ] **Step 2: Dim non-selected places**

Update place layer paint expressions so selected places use strong radius/opacity and non-selected visible places dim when another place is selected. Use GeoJSON feature properties, not DOM markers.

- [ ] **Step 3: Highlight the selected place route**

Update `buildRouteFeatureCollection(days, selectedDay, selectedPlace?.day ?? null)` so the selected place's day route is active when the user has not selected a specific day.

- [ ] **Step 4: Verify with TypeScript**

Run:

```bash
npm run typecheck
```

Expected: no TypeScript errors.

## Task 3: First-Screen AI-Native Generation Flow

**Files:**

- Modify: `frontend/components/trip/TripGenerationShell.tsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Remove the landing gate**

Make the input panel visible on first load over the Mapbox globe. Keep `StarfieldLanding.tsx` untouched but unused.

- [ ] **Step 2: Replace timeline logic with helper steps**

Import `getStageSteps` from `agent-copy.ts` and render stages as extract, ground, base, plan, approve with one-line details.

- [ ] **Step 3: Move decision-copy functions to helper**

Replace local title/evidence/tradeoff/next-action helpers with imports from `agent-copy.ts`.

- [ ] **Step 4: Add plan approval placeholder**

When status is `trip_ready`, add a compact final section with an "Approve plan" button that toggles a visible booking handoff placeholder. The copy must say it is a placeholder and must not imply real payment or booking.

- [ ] **Step 5: Run unit tests and typecheck**

Run:

```bash
npm run test:unit
npm run typecheck
```

Expected: both pass.

## Task 4: Minimal Panels And Place Rationale

**Files:**

- Modify: `frontend/components/trip/LeftTripPanel.tsx`
- Modify: `frontend/components/trip/RightTripPanel.tsx`
- Modify: `frontend/components/trip/PlaceIntelPanel.tsx`
- Modify: `frontend/components/trip/SelectedPlaceCard.tsx`

- [ ] **Step 1: Tighten left panel hierarchy**

Reduce large type, keep destination/dates high signal, and keep days/categories compact.

- [ ] **Step 2: Rename right tabs**

Use "Agent" and "Why this" to align with the demo story.

- [ ] **Step 3: Reframe place intel**

Use sections named "Why chosen", "What to do there", "Evidence", and "Travel fit". Keep source URL and directions link.

- [ ] **Step 4: Simplify selected-place card**

Make the floating card a quick rationale summary, preserving lock and view-intel actions.

- [ ] **Step 5: Run TypeScript**

Run:

```bash
npm run typecheck
```

Expected: no TypeScript errors.

## Task 5: Build And Visual Verification

**Files:**

- No planned source edits unless verification exposes a concrete defect.

- [ ] **Step 1: Run unit tests**

```bash
npm run test:unit
```

Expected: all tests pass.

- [ ] **Step 2: Run typecheck**

```bash
npm run typecheck
```

Expected: no TypeScript errors.

- [ ] **Step 3: Run production build**

```bash
npm run build
```

Expected: Next.js build succeeds.

- [ ] **Step 4: Run local dev server**

```bash
npm run dev
```

Expected: server starts on an available localhost port.

- [ ] **Step 5: Inspect with Browser**

Open the local URL in the in-app browser. Verify:

- First screen shows Mapbox globe and input panel without a click gate.
- No visible text overlap at desktop width.
- Missing backend state still leaves the input flow usable.
- Right panel and bottom rail do not obscure the selected place card badly.
- Map container is nonblank when a token is present.

## Self-Review

- Spec coverage: The plan covers frontend-only focus, Mapbox docs usage, AI-native decision visibility, minimal UI, selected map highlighting, route navigation, place rationale, and booking placeholder.
- Placeholder scan: No step uses implementation placeholders; backend work is explicitly out of scope.
- Type consistency: `GenerationStatusForCopy`, `StageStep`, `TripPlace`, `TripDay`, `TripHotelBase`, and `ExtractResponse` are referenced consistently across helper tests and component imports.
