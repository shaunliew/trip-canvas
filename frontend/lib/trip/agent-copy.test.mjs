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
