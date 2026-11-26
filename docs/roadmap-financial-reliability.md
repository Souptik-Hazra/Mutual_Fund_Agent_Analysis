# Authoritative Delivery Roadmap — Mutual Fund Agent Analysis

**Repository:** `Souptik-Hazra/Mutual_Fund_Agent_Analysis`  
**Default branch:** `main`  
**Operating model:** Personal, local-first Indian mutual-fund research application  
**Supported CI:** Python 3.11 backend; Node.js 22 frontend

## Current project baseline

Phases 0–21 and P0/P1 have previously been delivered on `main`. The existing FastAPI, PostgreSQL, React/Vite, LangChain/LangGraph, deterministic financial analytics, fund/category/portfolio intelligence, security observations, events, social research and document retrieval capabilities must be extended rather than rebuilt.

Financial calculations remain deterministic backend operations. LLMs may route, retrieve and explain evidence, but must not calculate or overwrite NAV, returns, XIRR, portfolio exposure or other financial values. Qdrant remains optional and private; PostgreSQL lexical retrieval is the fallback.

## P2 — Data coverage, reliability and operational validation

| ID | Priority | Current status | Verified scope / remaining acceptance gate |
|---|---|---|---|
| P2-01 | AMC disclosure adapters | **Partial** | Existing normalized CSV/XLSX ingestion handles common AMC/SEBI header variants and retains source hashes, publication/effective dates and unresolved holdings. AMC-specific adapters are not accepted as complete until official sample files from each supported AMC have been mapped and tested. |
| P2-02 | Scheme master and expense-ratio automation | **Partial** | Effective-dated scheme metadata observations and import paths exist. Automated authoritative bulk scheme-master refresh, expense-ratio history, lifecycle transitions and rename/merger reconciliation remain open. |
| P2-03 | Official IDCW source integration | **Partial** | Versioned IDCW observations, supersession history and verified-source coverage attestations exist; unverified/incomplete distributions are blocked from reinvested total-return calculations. Direct official AMC distribution adapters and real notice reconciliation remain open. |
| P2-04 | AMFI/MFAPI/Nifty validation | **Implemented; live run pending** | `mfa-audit-local --live` now reports date quality, duplicates, ordering/window defects and AMFI/MFAPI NAV reconciliation. Live execution against a selected scheme and Nifty TRI window has not been recorded; mocked tests are not counted as live validation. |
| P2-05 | Twelve Data validation | **Partial; credentials gated** | The quote adapter enforces exact returned symbol/exchange identity and has a gated audit probe. The probe is quote-only and explicitly does not infer historical prices, full fundamentals, corporate actions or plan-wide entitlement. A real key and confirmed exchange entitlement are required for live validation. |
| P2-06 | Qdrant lifecycle management | **Implemented; CI verification pending** | Semantic chunks use stable deterministic point IDs; reindex removes all prior document points before adding the new chunk set, preventing stale trailing chunks. Document deletion now requires successful vector cleanup before lexical rows are removed. Unconfigured Qdrant is treated as no semantic index; lexical retrieval remains authoritative. |
| P2-07 | Qdrant integration tests | **Implemented; CI verification pending** | A disposable Qdrant integration test covers same-ID upsert/retry, metadata filtering, document-scoped deletion and isolation from another document. The test uses a temporary collection and no production credentials. Failure-injection and full application-embedding integration remain additional coverage. |
| P2-08 | Corporate-event reliability | **Implemented; CI verification pending** | Event listing supports timezone-aware historical `as_of` queries by resolving the event revision active at that instant. Publication/effective dates and historical evidence metadata are retained in the response; event revision and API/frontend contract tests are added. |
| P2-09 | Social data governance | **Partial** | Collection is fail-closed unless the source registry contains a terms URL, explicit terms-review/access-confirmation flags and review timestamp. Retention expiry is applied to persisted posts. A human review of current Reddit/X terms, attribution and account entitlements is still required before enabling either connector. |
| P2-10 | Agent evaluation | **Partial** | The offline evaluation framework and deterministic specialist routing/evidence tests exist. Numerical parity, labelled unsupported-claim cases and coverage across every specialist still need expansion and measured thresholds. |
| P2-11 | Dependency/security scanning | **Partial** | Backend CI now includes strict `pip-audit`. Frontend dependency auditing remains gated by the missing committed npm lockfile. A complete secrets/authentication/input/logging review and documented upgrade process remain open. |
| P2-12 | Operational validation | **Verified** | The isolated PostgreSQL + Qdrant backup/restore drill passed in workflow run [45764435102](https://github.com/Souptik-Hazra/Mutual_Fund_Agent_Analysis/actions/runs/45764435102), backup-restore job. The drill creates a unique Compose project and disposable volumes, mutates both services, restores both, and verifies a database row and Qdrant point. |

### P2 external acceptance gates

- Supply representative official AMC portfolio disclosure files and confirm publication cadence before adding AMC-specific adapters.
- Identify authoritative AMC/AMFI IDCW notices and verify ex-date, record date, payment date, option and per-unit amount before attesting coverage.
- Run the live AMFI/MFAPI/Nifty audit for a known scheme and benchmark interval; save the generated report with the actual run date and provider errors.
- Provide a valid Twelve Data key and confirm the account's permitted NSE/BSE access before running the quote probe. A successful quote proves only that specific endpoint/instrument request.
- Review Reddit/X terms and current account permissions manually; keep the sources disabled until that review is recorded.
- Extend agent evaluation to deterministic numeric parity and specialist-specific abstention/evidence cases.

## P3 — Maintainability and documentation

| ID | Priority | Current status | Verified scope / remaining acceptance gate |
|---|---|---|---|
| P3-01 | Documentation reconciliation | **Partial** | README project status now points to the actual P2/P3 acceptance gates. Continue reconciling feature descriptions against merged implementation and remove any remaining stale claims. |
| P3-02 | Authoritative roadmap | **Implemented** | This document is the single P2/P3 delivery ledger with explicit statuses and acceptance gates. Historical phase notes remain supporting implementation records, not competing current roadmaps. |
| P3-03 | Assistant capability registry | **Implemented; CI verification pending** | `/assistant/capabilities` and frontend Overview expose the eight routed capabilities: fund, category, portfolio, actual exposure, security, events, social and documents. Registry IDs match the LangGraph intent names. |
| P3-04 | Reproducible frontend installation | **Implemented** | `frontend/package-lock.json` is committed, CI installs with `npm ci`, and Node.js 22 is pinned in the frontend workflow. The npm cache key now uses the lockfile so dependency changes invalidate the cache correctly. |
| P3-05 | Code cleanup | **Partial** | Cleanup has been limited to the Qdrant lifecycle and directly touched request/route logic. A broader unused-code/dead-component review remains open and must preserve API contracts. |
| P3-06 | Observability and integration limitations | **Implemented; CI verification pending** | API requests receive a validated/generated `X-Request-ID`; assistant runs generate a separate `research_run_id` returned in streaming/non-streaming responses, included in SSE progress frames, propagated through LangGraph nodes and attached to specialist completion/limited logs. HTTP logs retain request ID, method, path, status and duration without query strings. Provider entitlements, freshness and access limitations remain documented in the relevant source/phase notes. |

## CI and Git workflow contract

- All implementation changes are committed directly to the existing `main` branch; no feature branches or pull requests.
- Backend CI is Python 3.11 only. Keep Node.js 22 frontend tests/build.
- Live-provider checks remain explicitly gated and must never be represented by mocked tests.
- Qdrant integration tests use disposable service/collections. Backup/restore uses an isolated Compose project and disposable volumes.
- Do not weaken test coverage or mark a priority complete solely because code or documentation was added.

## Completion criteria

P2/P3 are complete only when every remaining external gate above has been either verified with evidence or explicitly documented as unavailable, the complete backend/frontend/agent/backup CI is green on `main`, the frontend lockfile is committed and cache-keyed, and the final code review confirms that financial methodology, provenance, historical `as_of` behaviour and local-only security boundaries remain intact.

## Explicitly out of scope

Public hosting, multi-user accounts, cloud deployment, production authentication, multi-tenancy, automated investing/trading and public exposure of the local development API.
