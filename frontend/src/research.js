export function buildDocumentSearchPath(query, schemeCode, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (schemeCode !== undefined && schemeCode !== null && String(schemeCode).trim() !== "") {
    params.set("scheme_code", String(schemeCode));
  }
  return `/documents/search?${params.toString()}`;
}

export function eventRows(payload) {
  return Array.isArray(payload?.events) ? payload.events : [];
}
