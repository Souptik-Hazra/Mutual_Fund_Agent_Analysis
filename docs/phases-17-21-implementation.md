# Phases 17–21 implementation notes

This increment extends the Phase 13–16 branch. It deliberately reuses the existing immutable
security observation table, AMC portfolio disclosures, LangGraph supervisor, Qdrant adapter,
and React/Vite workspace rather than introducing duplicate persistence models or agents.

## Phase 17 — Underlying security and corporate intelligence

- Added `POST /api/v1/market-data/security-observations` for dated, source-attributed stock observations.
- Validates timezone-aware observation timestamps, positive prices, date ordering, bounded corporate-event lists, allowed fundamental metric names, and finite decimal values.
- Stores fundamentals and corporate events in the existing immutable `security_market_observations` record. Operator-submitted events are explicitly marked unverified.
- Added `GET /api/v1/market-data/securities/{security_key}` with quote freshness, fundamentals as-of/freshness, observation history, corporate events, and matching positions from the latest eligible AMC disclosure per scheme.
- Missing fundamentals and market data remain unavailable; they are not inferred from NAV or fund returns.

## Phase 18 — LangGraph research orchestration

- Added a deterministic `security` specialist intent for stock valuation/fundamental questions.
- The specialist derives underlying equity security keys from the latest dated AMC disclosures and attaches source references for available observations.
- Existing deterministic fund/portfolio/event/document tools remain the source of numerical and factual outputs. LLM synthesis remains optional and evidence-bounded.

## Phase 19 — Financial document intelligence

- Replaced the single-channel retrieval branch with lexical + optional Qdrant semantic retrieval.
- Uses reciprocal-rank fusion on stable document/chunk identity; raw lexical and vector scores are never compared directly.
- Persists source key and canonical URL in newly indexed vector metadata; existing Qdrant collections should be reindexed to backfill this metadata.
- Preserves page/chunk/document provenance and reports candidate counts and retrieval mode.
- Added opt-in OCR for scanned pages. Enable `DOCUMENT_OCR_ENABLED=true`, install `pip install -e '.[ocr]'`, and install the Tesseract OCR executable on the host. OCR is disabled by default.
- PDF ingestion remains page-labelled; unsupported or unreadable documents fail with an explicit error rather than silently creating empty chunks.

## Phase 20 — React/Vite research workspace

Added three integrated views:
- **Fund Profile** — consolidated performance, risk, category, benchmark, portfolio disclosure and stored event sections.
- **Actual Exposure** — investor-ledger-weighted look-through exposure using units × latest accepted reconciled NAV.
- **Security Intelligence** — quote/fundamental freshness, corporate events and fund positions for a normalized security key.

These views use the existing API contracts and shared scheme selection. Existing screens are retained.

## Phase 21 — Financial reliability and evaluation

- Expanded migration-head regression to include revision `0012_category_benchmarks`.
- Added tests for security-observation validation, abstention on missing data, specialist routing, and reciprocal-rank fusion.
- Added security intent to the evidence-grounding contract and routing evaluation dataset.
- Existing multi-Python CI still needs to pass before this branch is considered validated.

## Operational boundaries

- Twelve Data remains opt-in and its NSE/BSE entitlement and permitted use must be confirmed by the operator.
- The new security-observation endpoint accepts data only from an enabled source registry entry; it does not independently authenticate or verify the publisher's claims.
- Corporate events are stored as reported/unverified unless separately reviewed through the evidence workflow.
- No automatic live NSE/BSE market feed, analyst recommendation, future-return prediction, or cloud deployment is introduced.
