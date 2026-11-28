import test from "node:test";
import assert from "node:assert/strict";
import { isPositiveNumber, isValidDateRange, validateTransactionDraft } from "./validation.js";

test("date ranges require real ISO dates in chronological order", () => {
  assert.equal(isValidDateRange("2024-01-01", "2024-12-31"), true);
  assert.equal(isValidDateRange("2024-12-31", "2024-01-01"), false);
  assert.equal(isValidDateRange("2024-02-30", "2024-03-01"), false);
  assert.equal(isValidDateRange("", "2024-03-01"), false);
});

test("positive numeric inputs reject empty, zero, negative and non-finite values", () => {
  for (const value of [null, undefined, "", " ", "0", 0, "-1", "NaN", Infinity]) {
    assert.equal(isPositiveNumber(value), false);
  }
  for (const value of ["0.01", 1, "100.25"]) assert.equal(isPositiveNumber(value), true);
});

test("transaction validation requires valid date, amount, units and optional NAV", () => {
  const base = {
    transactionDate: "2026-11-27",
    type: "purchase",
    amount: "1000",
    units: "10",
    nav: "100",
  };
  assert.equal(validateTransactionDraft(base, "2026-11-28"), "");
  assert.match(validateTransactionDraft({ ...base, transactionDate: "2026-12-01" }, "2026-11-28"), /not in the future/);
  assert.match(validateTransactionDraft({ ...base, amount: "0" }, "2026-11-28"), /amount/);
  assert.match(validateTransactionDraft({ ...base, units: "" }, "2026-11-28"), /Units/);
  assert.match(validateTransactionDraft({ ...base, nav: "-2" }, "2026-11-28"), /NAV/);
  assert.equal(validateTransactionDraft({ ...base, type: "charges", units: "" }, "2026-11-28"), "");
});
