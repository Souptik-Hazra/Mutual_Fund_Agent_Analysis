export function buildDocumentSearchPath(query, schemeCode, limit = 8) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (schemeCode !== undefined && schemeCode !== null && String(schemeCode).trim() !== "") {
    params.set("scheme_code", String(schemeCode));
  }
  return `/documents/search?${params.toString()}`;
}

export function eventRows(payload) {
  if (Array.isArray(payload?.events)) return payload.events;
  if (Array.isArray(payload?.items)) return payload.items;
  return [];
}
