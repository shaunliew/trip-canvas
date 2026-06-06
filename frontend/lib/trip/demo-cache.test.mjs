import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function importDemoCacheModule() {
  const source = await readFile(new URL("./demo-cache.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(transpiled).toString("base64");

  return import(`data:text/javascript;base64,${encoded}#${Date.now()}`);
}

const originalFetch = globalThis.fetch;
const originalBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalBackendUrl === undefined) {
    delete process.env.NEXT_PUBLIC_BACKEND_URL;
  } else {
    process.env.NEXT_PUBLIC_BACKEND_URL = originalBackendUrl;
  }
});

test("demo Reel constants expose the four hackathon Reel URLs", async () => {
  const demoCache = await importDemoCacheModule();

  assert.deepEqual(demoCache.DEMO_REEL_URLS, [
    "https://www.instagram.com/reel/DYbmT-SNzVK/",
    "https://www.instagram.com/reel/DYM_I5IvLSv/",
    "https://www.instagram.com/reel/DYGH3jFBZHz/",
    "https://www.instagram.com/reel/DXwcVVliX3B/",
  ]);
  assert.equal(demoCache.DEMO_REEL_INPUT, demoCache.DEMO_REEL_URLS.join("\n"));
});

test("loadBackendDemoCache fetches the backend demo-cache endpoint", async () => {
  process.env.NEXT_PUBLIC_BACKEND_URL = "http://localhost:8000/";
  const payload = {
    source: "cache",
    places: [{ name: "Tokyo Tower", category: "landmark", city_or_region_guess: "Tokyo", confidence: 0.9, evidence_caption_quote: "Tokyo Tower" }],
    hotel_base: { source: "cache", hotel_candidates: [] },
    itinerary: { source: "cache", days: [] },
  };
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return {
      ok: true,
      json: async () => payload,
    };
  };

  const demoCache = await importDemoCacheModule();
  const result = await demoCache.loadBackendDemoCache();

  assert.equal(result, payload);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://localhost:8000/demo-cache");
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers.Accept, "application/json");
});

test("loadBackendDemoCache surfaces backend detail on failure", async () => {
  process.env.NEXT_PUBLIC_BACKEND_URL = "http://backend.test";
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ detail: "itinerary cache missing" }),
  });

  const demoCache = await importDemoCacheModule();

  await assert.rejects(
    () => demoCache.loadBackendDemoCache(),
    /itinerary cache missing/,
  );
});
