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
});
