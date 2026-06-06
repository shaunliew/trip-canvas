import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function importMapStyleModule() {
  const source = await readFile(new URL("./map-style.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(transpiled).toString("base64");

  return import(`data:text/javascript;base64,${encoded}`);
}

const mapStyle = await importMapStyleModule();

test("buildActiveAwareLineWidth keeps zoom as the top-level interpolate input", () => {
  const expression = mapStyle.buildActiveAwareLineWidth({
    zoomStops: [
      [10, 9, 3.5],
      [14, 16, 6],
      [16, 21, 8],
    ],
  });

  assert.equal(expression[0], "interpolate");
  assert.deepEqual(expression[1], ["linear"]);
  assert.deepEqual(expression[2], ["zoom"]);
  assert.deepEqual(expression[3], 10);
  assert.deepEqual(expression[4], ["case", ["boolean", ["get", "active"], false], 9, 3.5]);
  assert.equal(JSON.stringify(expression.slice(4)).includes('["zoom"]'), false);
});
