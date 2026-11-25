# Next Roadmap — Financial Correctness and Research Reliability

**Status:** Active delivery; baseline CI verified on 2026-11-25  
**Target branch:** `main`  
**Scope:** Local-first, single-user Indian mutual-fund research application. No public hosting, multi-user accounts, cloud deployment, autonomous trading, or public API exposure.

## Current baseline (already merged)

The following are delivered and must be extended rather than rebuilt:

- Phases 1–3: FastAPI/PostgreSQL foundation, MFAPI and AMFI NAV ingestion/reconciliation, Nifty TRI ingestion, deterministic returns/risk/drawdown analytics, scheme discovery, single-fund analytics, and 2–5-fund comparison.
- Phase 4: canonical entity identity, source registry, evidence provenance, aliases/identifiers, relationships, and deterministic resolution.
- Phase 5: portfolio snapshots/holdings ingestion, sector and asset allocation, concentration, holdings history/change, fund overlap, and stock-to-fund exposure.
- Phase 6: event ingestion and fund exposure using the portfolio snapshot effective on the event date.
- Phase 7: opt-in Reddit/X adapters and social analytics; providers are disabled by default.
- Phase 8: PDF extraction, page-aware chunks, lexical retrieval, optional Qdrant semantic retrieval, and cited document Q&A.
- Phases 9–11: LangGraph orchestration, React/Vite local workspace, and offline routing/retrieval evaluation utilities.

Daily, weekly, monthly, quarterly, yearly, and custom date-range analysis are part of the intended contract. The backend already accepts explicit date ranges and annualization frequency; multi-fund comparison already supports 2–5 schemes. The remaining task is to verify and expose these controls consistently in the UI and API, not to create a second analytics engine.

## Delivery principles

1. Financial calculations remain deterministic Python services; LLMs may explain results but must never calculate or overwrite financial metrics.
2. Never silently forward-fill, interpolate, invent NAV/TRI, resolve ambiguous identities, or convert unverified reports/posts into confirmed facts.
3. Every result must carry its observation window, source, as-of/retrieval time, coverage, methodology, and limitations where relevant.
4. Use Decimal for monetary/NAV arithmetic and explicit cash-flow conventions for investor returns.
5. Implement source-specific ingestion only after its official availability, terms, schema, update cadence, and retention rights are checked.
6. Keep schema migrations reversible where practical, ingestion idempotent, and provider payloads auditable.
7. A phase is complete only after tests, documentation, and CI pass on the supported Python matrix.

---

## Phase 0 — Main-branch baseline and gap verification

**Goal:** Establish the actual working baseline before changing financial behaviour.

- [x] Run the complete CI-equivalent suite against current `main`: Ruff, formatting, pytest with PostgreSQL, Docker Compose validation/build, frontend tests/build, and offline agent evaluation (main commit `eb3804be`, successful run `45623391232`).
- [ ] Verify the latest Alembic migration chain from an empty database and from the previous supported schema.
- [ ] Exercise live MFAPI, AMFI, and Nifty TRI retrieval with bounded date ranges; record provider failures/schema changes without making CI depend on live services.
- [ ] Audit every API request/response schema against the frontend's actual request bodies and rendered response shapes.
- [ ] Generate a data-coverage report: schemes, NAV date ranges, reconciliation status, benchmark series, metadata completeness, portfolio snapshots, events, social sources, and document index.
- [ ] Record reproducible baseline metrics and known limitations.

**Exit criteria:** A checked-in audit report identifies each verified capability, missing source, coverage gap, and reproducible defect. No implementation is marked complete solely because its route or model exists.

## Phase 1 — Investor cash-flow returns: SIP, lump sum, and XIRR

**Goal:** Calculate the investor's realized experience separately from fund NAV performance.

- [x] Define a typed cash-flow and transaction contract with dates, explicit transaction types/cash-flow signs, INR currency, optional folio reference, units, and NAV.
- [x] Support SIP, lump-sum purchases, additional purchases, redemptions, switches, dividend payouts, and supplied charges/taxes with explicit transaction types.
- [x] Implement deterministic dated XIRR with bounded-rate search, multiple-root/no-root failure states, and bounded bisection.
- [x] Implement exact-date SIP simulation separately from actual transaction-ledger XIRR; simulated SIP output is explicitly labelled.
- [x] Add invested amount, current value, realized proceeds, unrealized value, absolute gain, XIRR, and missed-installment coverage to reports.
- [ ] Add test fixtures for irregular dates, missed SIPs, partial redemptions, same-day flows, leap years, zero/invalid flows, and non-convergence.
- [x] Expose simulated-versus-actual return basis and core assumptions through the API and Investments UI.

**Exit criteria:** Independent known-answer fixtures and property/invariant tests pass; the UI distinguishes fund CAGR from investor XIRR and simulated SIP outcomes.

## Phase 2 — IDCW-aware total-return methodology

**Goal:** Avoid understating returns for IDCW/distribution options.

- [ ] Research and register authoritative distribution sources, including ex-date, record/payment date, per-unit amount, applicable option, and source provenance.
- [ ] Add versioned distribution observations with idempotent ingestion and conflict audit.
- [ ] Implement a documented reinvested-distribution total-return methodology using the correct ex-date convention and available NAVs.
- [ ] Keep Growth NAV returns, IDCW payout cash-flow returns, and reinvested IDCW total returns distinct.
- [ ] Define treatment for taxes, exit loads, reinvestment timing, missing distributions, and revised/cancelled disclosures; do not assume investor-specific tax outcomes.
- [ ] Add fund/benchmark comparison safeguards so a price/NAV-only series is not mislabelled as total return.
- [ ] Surface missing distribution coverage and reject incomplete total-return claims.

**Exit criteria:** Independently calculated test cases validate ex-date adjustments and reinvestment; all API/UI labels state the return basis.

## Phase 3 — Scheme master and product metadata completeness

**Goal:** Improve the accuracy of scheme discovery and filtering.

- [ ] Add/verify lifecycle-aware scheme-master ingestion, including open-ended, close-ended, and interval schemes where official historical data is available.
- [ ] Implement bulk/daily refresh with bounded requests, retry/backoff, checkpointing, resumability, and per-scheme outcomes.
- [ ] Validate direct/regular plan and Growth/IDCW option classification from authoritative source fields; preserve unknown/ambiguous values rather than infer from names.
- [ ] Add source-backed expense-ratio observations with effective dates, plan/option mapping, source, and freshness.
- [ ] Audit AMC, category, scheme type, benchmark mapping, launch/closure dates, and ISIN coverage.
- [ ] Add metadata change history rather than overwriting historical values without provenance.
- [ ] Add source-coverage and staleness indicators to scheme details and filters.

**Exit criteria:** Metadata fields are source-backed, effective-dated, auditable, and correctly filtered; no inferred plan labels are presented as verified.

## Phase 4 — Analytics configuration and additional risk measures

**Goal:** Complete the analysis contract without duplicating the existing analytics core.

- [ ] Verify daily, weekly, monthly, quarterly, yearly, and custom date-window calculations against known-answer fixtures and actual observation spacing.
- [ ] Ensure UI controls map to the existing `start_date`, `end_date`, and `periods_per_year` API contract consistently.
- [ ] Add explicit comparison duration/frequency controls for 2–5 funds; preserve exact common-date alignment and report the resulting common window.
- [x] Implement tracking error and information ratio using exact aligned fund/benchmark periodic returns and explicit annualization.
- [ ] Document whether returns are arithmetic or geometric for every annualized metric; avoid mixing methodologies in the same comparison.
- [ ] Validate risk-free-rate conventions, downside deviation, beta, alpha, volatility, and coverage diagnostics across frequencies.
- [ ] Add base-100 indexed performance series for visual comparison, clearly labelled as normalized growth rather than absolute return.
- [ ] Ensure incomplete or stale windows return warnings/undefined metrics rather than fabricated values.

**Exit criteria:** Each frequency has deterministic fixtures; benchmark metrics use exact interval alignment; charts and tables disclose normalized versus absolute values.

## Phase 5 — Portfolio holdings data quality and intelligence

**Goal:** Strengthen the existing portfolio subsystem rather than rebuild it.

- [ ] Build source-specific AMC disclosure adapters only for verified official file formats and publication schedules.
- [ ] Add schema/version detection and mapping tests for CSV/XLSX/PDF-derived holdings; retain manual import as a supported fallback.
- [ ] Validate ISIN/security resolution, corporate actions/name changes, cash/debt/derivative/other asset classes, and unresolved holdings.
- [ ] Add snapshot coverage metrics, unresolved-weight percentage, source freshness, and effective-date confidence.
- [ ] Verify sector allocation, concentration/HHI, overlap, holdings change, and stock-to-fund exposure against independent fixtures.
- [ ] Add reconciliation for corrected/reissued portfolio disclosures and audited entity merge workflow before any fuzzy matching.
- [ ] Add historical AMC/scheme relationship validity review where provider metadata changes over time.

**Exit criteria:** Every portfolio metric reports coverage and unresolved exposure; corrected disclosures are traceable; no unresolved security is silently dropped from totals.

## Phase 6 — Evidence, news, social, and document reliability

**Goal:** Make all research claims traceable, rights-aware, and time-aware.

- [x] Add source-specific retention enforcement and PostgreSQL purge verification before enabling Reddit/X collection. Provider terms/access review still gates enabling either source.
- [ ] Review current provider access, attribution, terms, and rate limits; keep unsupported or unapproved connectors disabled.
- [ ] Distinguish official disclosure, reputable reporting, reported/unverified event, confirmed event, opinion, rumour, and speculation in schemas and UI.
- [ ] Add publication-time versus retrieval-time versus effective-time handling, source freshness, duplicate detection, and correction/retraction tracking.
- [ ] Ensure event-to-fund exposure uses the holdings snapshot effective on the event date and reports missing historical coverage.
- [ ] Harden document extraction for malformed/encrypted PDFs and explicitly report that scanned-PDF OCR is unsupported until implemented and tested.
- [ ] Test lexical fallback and optional Qdrant retrieval, index consistency, chunk provenance, citation resolution, and deletion/purge behaviour.
- [ ] Treat social posts and document text as untrusted input; test prompt injection and unsupported-claim abstention.
- [ ] Add auditable entity merge/reconciliation and reviewed temporal validity workflows; never auto-merge ambiguous aliases.

**Exit criteria:** Claims have resolvable evidence and timestamps; unverified content remains labelled; retention and deletion are tested; disabled sources cannot be queried accidentally.

## Phase 7 — Research agent and evaluation quality

**Goal:** Evaluate financial correctness and evidence quality, not just routing.

- [ ] Expand the curated evaluation set across single-fund, multi-fund, portfolio, events, social, and document intents.
- [ ] Add numerical parity tests: agent outputs must match deterministic analytics API results exactly within documented Decimal/serialization tolerances.
- [ ] Evaluate citation precision/coverage, source authority, evidence freshness, temporal correctness, and unsupported-claim rate.
- [ ] Test ambiguity, missing data, conflicting NAVs, stale snapshots, unavailable providers, empty retrieval, and out-of-scope questions.
- [ ] Add adversarial tests for prompt injection in PDFs/social content and ensure untrusted content cannot alter tool policy.
- [ ] Measure deterministic fallback behaviour when no LLM key exists or the model provider fails.
- [ ] Add regression thresholds and fail CI for critical financial or evidence-contract regressions; keep external network tests separately gated.

**Exit criteria:** Offline evaluation is reproducible; critical financial facts are grounded in deterministic tools; the assistant abstains when evidence is insufficient.

## Phase 8 — Local operations and security hardening

**Goal:** Make the personal local installation robust without turning it into a public service.

- [ ] Review API input limits, upload size/type validation, path handling, SQL/query bounds, and SSRF protections for registered source URLs.
- [ ] Add bounded timeouts, retry policies, rate limiting/concurrency caps, and useful provider error states.
- [ ] Review cache keys and invalidation for NAV, benchmark, metadata, event, social, and document retrieval data.
- [ ] Add structured logs with request/run IDs while avoiding API keys, personal transaction data, and unnecessary social/document content.
- [ ] Verify localhost-only binding defaults and safe CORS; do not add public deployment/authentication.
- [x] Document PostgreSQL/Qdrant backup, restore, migration, and recovery procedures; add checksum-protected scripts and CI shell validation.
- [ ] Execute and verify a full restore against a disposable local PostgreSQL/Qdrant copy before relying on backups for recovery.
- [ ] Add database constraints/index review and query plans for large NAV/holdings histories.
- [ ] Define local audit-data retention and purge controls, including raw provider sync payloads.
- [ ] Add dependency/security scanning and a documented upgrade process.

**Exit criteria:** A clean local setup, migration, backup, restore, and recovery test succeeds; no secrets or sensitive local data are committed.

---

## Execution order and dependency gates

| Order | Work package | Depends on |
|---|---|---|
| 0 | Baseline audit | Current `main` |
| 1 | SIP/XIRR | Cash-flow schema and transaction conventions |
| 2 | IDCW total returns | Authoritative distribution data and Phase 1 cash-flow primitives where relevant |
| 3 | Scheme master and metadata | Verified AMFI/AMC/provider source contracts |
| 4 | Analytics configuration and risk metrics | Verified data coverage and stable return-series conventions |
| 5 | Portfolio data quality | Canonical identifiers and historical evidence |
| 6 | Evidence/news/social/document reliability | Source registry and rights/retention review |
| 7 | Agent evaluation quality | Stable deterministic analytics and evidence contracts |
| 8 | Local operations hardening | Integrated application and data flows |

Parallel work is allowed only when it does not change shared financial contracts or migrations concurrently. Each work package should use a dedicated feature branch and PR; merge only after review, CI, migration checks, and regression evaluation.

## Definition of done for every PR

- Tests cover normal, boundary, missing, stale, conflicting, and invalid inputs.
- Financial logic has independent known-answer fixtures and uses Decimal where monetary precision matters.
- API schemas, frontend usage, and documentation agree.
- Migrations are tested from both empty and previous supported schemas.
- No silent data fabrication, fallback to a different scope, or unsupported certainty.
- Ruff, formatting, full pytest/PostgreSQL suite, Docker checks, frontend tests/build, and offline evaluation pass.
- README and this roadmap are updated with delivered scope and remaining limitations.

## Explicitly out of scope

Public hosting, cloud deployment, multi-user accounts, production authentication/authorization, multi-tenant data, automated investment execution, autonomous trading, and public exposure of the local development API.
