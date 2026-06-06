import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import ts from "typescript";

async function importItineraryUiModule() {
  const source = await readFile(new URL("./itinerary-ui.ts", import.meta.url), "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const encoded = Buffer.from(transpiled).toString("base64");

  return import(`data:text/javascript;base64,${encoded}`);
}

const itineraryUi = await importItineraryUiModule();

const places = [
  {
    id: "hotel",
    name: "The Royal Park Hotel Iconic Tokyo Shiodome",
    category: "hotel",
    day: 1,
    lat: 35.664,
    lng: 139.761,
    summary: "A practical Shiodome base.",
  },
  {
    id: "tsukiji",
    name: "Tsukiji Outer Market",
    category: "market",
    day: 1,
    lat: 35.665486,
    lng: 139.770667,
    summary: "Morning food crawl.",
    dayPlanText:
      "Morning: arrive at Tokyo Narita at 07:05 on the overnight Scoot nonstop from Singapore, take the rail transfer into Shiodome/Shimbashi, drop bags at The Royal Park Hotel Iconic Tokyo Shiodome, then walk to Tsukiji Outer Market for grilled seafood, tamagoyaki, and knife-shop browsing. Afternoon: keep the route light because this is an arrival day.",
  },
  {
    id: "tower",
    name: "Tokyo Tower",
    category: "landmark",
    day: 1,
    lat: 35.658581,
    lng: 139.745433,
    summary: "Golden-hour skyline stop.",
  },
  {
    id: "sensoji",
    name: "Senso-ji",
    category: "temple",
    day: 2,
    lat: 35.714765,
    lng: 139.796655,
    summary: "Old Tokyo temple streets.",
  },
];

const days = [
  {
    day: 1,
    title: "Arrival food loop",
    summary: "A practical first-day route from Shiodome to Tsukiji and Tokyo Tower.",
    placeIds: ["hotel", "tsukiji", "tower"],
    route: {
      coordinates: [
        [139.761, 35.664],
        [139.770667, 35.665486],
        [139.745433, 35.658581],
      ],
      durationMinutes: 42,
      distanceKm: 5.4,
    },
  },
  {
    day: 2,
    title: "Old Tokyo",
    summary: "Temple streets and snacks.",
    placeIds: ["sensoji"],
  },
];

test("buildRoutePreview returns an in-site day route summary for a selected place", () => {
  const preview = itineraryUi.buildRoutePreview(places[1], days, places);

  assert.equal(preview.day, 1);
  assert.equal(preview.title, "Arrival food loop");
  assert.equal(preview.routeLabel, "42 min route - 5.4 km");
  assert.deepEqual(
    preview.stops.map((stop) => [stop.id, stop.selected]),
    [
      ["hotel", false],
      ["tsukiji", true],
      ["tower", false],
    ],
  );
});

test("buildItineraryTimeline groups days with ordered stops and route labels", () => {
  const timeline = itineraryUi.buildItineraryTimeline(days, places, "tower");

  assert.equal(timeline.length, 2);
  assert.equal(timeline[0].selected, true);
  assert.equal(timeline[0].stopCount, 3);
  assert.equal(timeline[0].routeLabel, "42 min route - 5.4 km");
  assert.deepEqual(
    timeline[0].stops.map((stop) => stop.name),
    [
      "The Royal Park Hotel Iconic Tokyo Shiodome",
      "Tsukiji Outer Market",
      "Tokyo Tower",
    ],
  );
  assert.equal(timeline[1].routeLabel, "1 mapped stop");
});

test("splitItineraryTextSections preserves long morning copy instead of truncating it", () => {
  const sections = itineraryUi.splitItineraryTextSections(places[1].dayPlanText);

  assert.deepEqual(
    sections.map((section) => section.label),
    ["Morning", "Afternoon"],
  );
  assert.ok(sections[0].text.includes("overnight Scoot nonstop from Singapore"));
  assert.ok(sections[0].text.includes("The Royal Park Hotel Iconic Tokyo Shiodome"));
  assert.ok(sections[0].text.length > 180);
});
