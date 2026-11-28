const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const UNIT_TRANSACTION_TYPES = new Set(["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"]);

export function isValidDateRange(startDate, endDate) {
  if (!DATE_PATTERN.test(startDate || "") || !DATE_PATTERN.test(endDate || "")) return false;
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  return !Number.isNaN(start.getTime()) && !Number.isNaN(end.getTime()) &&
    start.toISOString().slice(0, 10) === startDate &&
    end.toISOString().slice(0, 10) === endDate &&
    startDate <= endDate;
}

export function isPositiveNumber(value) {
  if (value === null || value === undefined || String(value).trim() === "") return false;
  const number = Number(value);
  return Number.isFinite(number) && number > 0;
}

export function validateTransactionDraft(transaction, today) {
  if (!DATE_PATTERN.test(transaction.transactionDate || "")) return "Choose a valid transaction date.";
  const date = new Date(`${transaction.transactionDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== transaction.transactionDate) return "Choose a valid transaction date.";
  if (transaction.transactionDate > today) return "Choose a transaction date that is not in the future.";
  if (!isPositiveNumber(transaction.amount)) return "Transaction amount must be greater than zero.";
  if (UNIT_TRANSACTION_TYPES.has(transaction.type) && !isPositiveNumber(transaction.units)) return "Units must be greater than zero.";
  if (transaction.nav !== "" && transaction.nav != null && !isPositiveNumber(transaction.nav)) return "NAV must be greater than zero.";
  return "";
}
