# Phases 5–8: implementation notes

## Phase 5 — Portfolio intelligence

### Data model
- `portfolio_snapshots` stores one immutable disclosure version per scheme, effective date, source and content hash.
- `portfolio_holdings` stores security identifiers, ISIN, security name, sector, asset class, quantity, market value, currency and disclosed weight.
- Holdings support equity, debt, cash, derivatives, REIT/InvIT, gold and other assets. Asset class is not guessed during file import.
- Re-importing the same scheme/date/source/hash is idempotent. A changed source file creates a new version rather than overwriting history.

### Ingestion
- `POST /api/v1/portfolios/import`: normalized JSON payload.
- `POST /api/v1/portfolios/import-file`: CSV or XLSX upload from an AMC disclosure.
- CSV/XLSX headers: `security_key` or `isin`, `security_name`, `asset_class`, optional `sector`, `quantity`, `market_value`, `weight_pct`, `currency`.
- CSV/XLSX imports require a stable security key or ISIN and an explicit asset class.
- The source registry contains `amc_disclosures`. Source-specific AMC download endpoints and proprietary file layouts are not assumed to be uniform; map each AMC's published columns into this normalized contract.

### Analytics and endpoints
- `GET /api/v1/portfolios/{scheme_code}` (optional `as_of`)
- `GET /api/v1/portfolios/{scheme_code}/history`
- `GET /api/v1/portfolios/{scheme_code}/holdings`
- `GET /api/v1/portfolios/{scheme_code}/sectors`
- `GET /api/v1/portfolios/{scheme_code}/changes`
- `POST /api/v1/portfolios/compare`
- `GET /api/v1/securities/{security_key}/fund-exposure`

Outputs include top holdings, sector/asset allocation, weight coverage, HHI when disclosure weight coverage is sufficiently complete, pairwise overlap and consecutive-snapshot differences. Snapshot differences are not proof of trades: issuer naming, classification and corporate actions can also change.

## Phase 6 — News and event intelligence

- `market_events` stores event type, status, event date, publication time, source, entity link, evidence link and supersession metadata.
- `POST /api/v1/events` accepts a normalized event with source/evidence references.
- `GET /api/v1/events/fund-exposure/{scheme_code}` maps company and sector events to the holdings snapshot effective on the event date.
- `GET /api/v1/events` filters by date, status and canonical entity.
- `POST /api/v1/events/collect/{source_key}?feed_url=...` ingests RSS/Atom from an enabled registered source.
- RSS feed URLs must use HTTPS and the exact host configured in that source's `data_sources.base_url`; redirects are disabled. Configure a verified feed URL for the relevant exchange/regulator source before calling the endpoint.
- Feed items are always labelled `reported` and evidence is `unverified`. The adapter never upgrades an RSS headline to confirmed status. Entity linking and event status changes require corroborating evidence.

## Phase 7 — Social intelligence

- Official API clients are provided for Reddit OAuth search and X API v2 recent search.
- `GET /api/v1/social/collect?source=reddit|x&q=...` collects recent posts after checking that the corresponding source registry row is enabled.
- Reddit and X source rows remain disabled by default. Enable only after reviewing the applicable developer terms, API tier, retention, attribution and deletion requirements. Add approved credentials to environment variables.
- `POST /api/v1/social/posts` accepts a normalized post and optional externally evaluated sentiment label/score/model.
- `GET /api/v1/social/analytics` aggregates discussion volume and supplied sentiment scores.
- `GET /api/v1/social/funds/{scheme_code}/sentiment?start_date=...&end_date=...` time-weights scored company sentiment by the fund holdings effective when each post was published and returns coverage.
- Collection persists provider IDs, URLs, hashes, timestamps and engagement metadata; raw text excerpts are not persisted. A global expiry (`SOCIAL_RETENTION_DAYS`, default 30 days) applies unless the source registry's `metadata.retention_days` provides a provider-specific override (1–365 days). Set the override from the applicable provider terms. Schedule `mfa-purge-expired-social` daily. The PostgreSQL integration suite verifies expired rows are removed while unexpired rows remain.
- The collector does not fabricate sentiment. Collected posts are marked `not_scored`; connect and evaluate a finance sentiment classifier before using sentiment analytics. Do not interpret discussion volume or engagement as credibility or a NAV predictor.

## Phase 8 — Document intelligence

- `research_documents` and `document_chunks` preserve uploaded document metadata, SHA-256 hash, effective/publication dates, extracted text and chunk provenance.
- `POST /api/v1/documents/upload` accepts text-based PDF files up to 25 MB. Scanned PDFs are rejected with an OCR-required message; OCR is not silently guessed.
- `GET /api/v1/documents` lists indexed documents.
- `GET /api/v1/documents/search?q=...` returns retrieved chunks with document/chunk citations.
- `POST /api/v1/documents/ask` asks the configured LLM to answer from retrieved excerpts, requires citations and treats document contents as untrusted input.
- Qdrant semantic retrieval is enabled in Docker Compose. The API falls back to PostgreSQL lexical retrieval when Qdrant or Gemini embedding credentials are unavailable. Set `GEMINI_API_KEY`, `QDRANT_URL`, and optional `QDRANT_API_KEY` to use embeddings.
- Answers are research assistance, not a substitute for the deterministic financial analytics services. Verify every cited source and date.

## Setup and migration

1. Update your local checkout to this feature branch.
2. Copy new settings from `.env.example`; add approved provider credentials only where needed.
3. Install the project with development and vector extras: `pip install -e ".[dev,vectors]"`.
4. Start services and migrate: `docker compose up -d db qdrant`, then `alembic upgrade head`.
5. Run API: `uvicorn mutual_fund_agent_analysis.main:app --reload`.
6. Open `/docs` for the versioned API contracts.

Migration `0007_research_intelligence` adds the six Phase 5–8 tables and the AMC disclosure source registry entry. Social sources remain opt-in.

## Deliberate integration boundaries

- No universal AMC holdings API is assumed. The normalized JSON/CSV/XLSX ingestion contract is stable; provider-specific download and table mapping can be added when the AMC source and terms are verified.
- RSS collection is generic and allowlisted, not a claim that NSE/BSE/SEBI publish a particular stable feed. A valid feed URL must be configured by the operator.
- Reddit/X access depends on approved API credentials and the user's access tier. Collection is disabled until explicitly enabled.
- Sentiment scoring is an input contract, not an unevaluated keyword heuristic.
- PDF OCR is not bundled. Scanned documents require a separately selected OCR pipeline.
- Qdrant semantic retrieval is optional; lexical retrieval remains available.
- LangGraph multi-agent orchestration belongs to Phase 9 and is intentionally not introduced in Phases 5–8.
