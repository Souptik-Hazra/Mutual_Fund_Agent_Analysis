import assert from "node:assert/strict";
import test from "node:test";

import { buildDocumentSearchPath, eventRows } from "../src/research.js";

test("document search omits an absent optional scheme code", () => {
  const url = new URL(buildDocumentSearchPath("expense ratio", undefined, 8), "http://localhost");
  assert.equal(url.searchParams.get("q"), "expense ratio");
  assert.equal(url.searchParams.get("limit"), "8");
  assert.equal(url.searchParams.has("scheme_code"), false);
});

test("document search includes a valid scheme code", () => {
  const url = new URL(buildDocumentSearchPath("expense ratio", 125497), "http://localhost");
  assert.equal(url.searchParams.get("scheme_code"), "125497");
});

test("event rows match the API's flat events response", () => {
  const rows = eventRows({ events: [{ event_id: 1, title: "Results" }] });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].title, "Results");
});

test("event rows safely handle an empty or malformed response", () => {
  assert.deepEqual(eventRows({}), []);
  assert.deepEqual(eventRows({ events: {} }), []);
  assert.deepEqual(eventRows({ items: {} }), []);
});


test("event rows normalize paginated event-search responses", () => {
  const rows = eventRows({ count: 1, items: [{ event_id: 8, title: "Dividend" }] });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].event_id, 8);
});

test("research stream consumes progress and final SSE events", async () => {
  const { streamRequest } = await import("../src/api.js");
  const originalFetch = globalThis.fetch;
  const frames = [
    'event: progress\ndata: {"node":"plan","message":"Planned","intents":["fund"]}\n\n',
    'event: complete\ndata: {"answer":"Completed","intents":["fund"],"results":{},"citations":[]}\n\n',
  ].join("");
  globalThis.fetch = async () => new Response(frames, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
  const progress = [];
  try {
    const result = await streamRequest("/assistant/research/stream", { question: "Show returns" }, (item) => progress.push(item));
    assert.equal(progress.length, 1);
    assert.equal(progress[0].node, "plan");
    assert.equal(result.answer, "Completed");
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("workspace does not assume NIFTY 50 and resolves effective benchmark mappings", async () => {
  const { readFile } = await import("node:fs/promises");
  const app = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  assert.equal(app.includes('useState("NIFTY 50")'), false);
  assert.match(app, /\/fund-intelligence\/schemes\/.*\/benchmark/);
  assert.match(app, /Benchmark TRI override \(optional\)/);
  assert.match(app, /selection\.benchmark\?\.code \|\| null/);
});


test("historical equity status passes the selected end date as API as_of", async () => {
  const { readFile } = await import("node:fs/promises");
  const component = await readFile(new URL("../src/AdvancedIntelligence.jsx", import.meta.url), "utf8");
  assert.match(component, /params\.set\(tab === "Fund Profile" \? "end_date" : "as_of", dateTo\)/);
  assert.match(component, /\/fund-intelligence\/schemes\/\$\{schemeCodes\[0\]\}\/profile/);
  assert.match(component, /\/market-data\/securities\/\$\{encodeURIComponent\(securityKey\.trim\(\)\)\}/);
});
