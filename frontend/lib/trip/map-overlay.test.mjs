import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function importMapOverlayModule() {
  const source = await readFile(new URL("./map-overlay.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(transpiled).toString("base64");

  return import(`data:text/javascript;base64,${encoded}`);
}

const mapOverlay = await importMapOverlayModule();

test("getMapCalloutPosition centers above a marker when there is room", () => {
  assert.deepEqual(
    mapOverlay.getMapCalloutPosition({
      marker: { x: 420, y: 280 },
      viewport: { width: 1024, height: 768 },
      callout: { width: 260, height: 120 },
    }),
    {
      left: 290,
      top: 136,
      anchorX: 130,
    },
  );
});

test("getMapCalloutPosition clamps near the left edge", () => {
  assert.deepEqual(
    mapOverlay.getMapCalloutPosition({
      marker: { x: 30, y: 260 },
      viewport: { width: 390, height: 844 },
      callout: { width: 220, height: 112 },
      margin: 16,
    }),
    {
      left: 16,
      top: 124,
      anchorX: 14,
    },
  );
});

test("getMapCalloutPosition flips below a top-edge marker", () => {
  assert.deepEqual(
    mapOverlay.getMapCalloutPosition({
      marker: { x: 220, y: 42 },
      viewport: { width: 430, height: 932 },
      callout: { width: 230, height: 120 },
      margin: 18,
    }),
    {
      left: 105,
      top: 66,
      anchorX: 115,
    },
  );
});
