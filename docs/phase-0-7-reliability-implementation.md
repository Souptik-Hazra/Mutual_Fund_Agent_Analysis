# Phases 0–7 reliability implementation notes

This implementation adds auditable financial-data contracts and conservative calculations. It does not manufacture upstream completeness or certify provider rights.

## Phase 0: coverage and provider audit

Run `mfa-audit-local` after applying migrations to create a local count/range report:

```bash
mfa-audit-local --output artifacts/local-coverage-audit.json
```

A bounded, read-only provider probe requires explicit scheme/index identifiers and dates (maximum 31 calendar days):

```bash
mfa-audit-local --live --scheme-code 125497 --benchmark-code "NIFTY 50" \
  --start-date 2026-11-01 --end-date 2026-11-25
```

The script reports MFAPI, AMFI and Nifty Indices outcomes separately. Live provider probes are deliberately excluded from ordinary CI because provider availability, rate limits and response changes are outside the repository's control. The API also exposes `GET /api/v1/audit/coverage`.

## Phase 1: investor cash-flow boundary coverage

Additional deterministic tests cover same-day cash-flow aggregation, leap-year actual-day XIRR and no-root rejection. Existing transaction-ledger and SIP tests remain the executable contract for partial redemptions, missed NAVs and the simulated-versus-actual basis.

## Phase 2: IDCW records and reinvested return

`scheme_metadata_observations` and `distribution_observations` retain source URLs, content hashes, effective dates, verification status and correction revisions. Distribution records are append-only by revision; a correction supersedes the former active revision.

The reinvested index applies `(ex-date NAV + distribution per unit) / prior NAV`, reinvesting on the ex-date at the published ex-date NAV. The separate payout index adds cumulative per-unit distribution cash without reinvestment or interest. The API is `GET /api/v1/schemes/{scheme_code}/idcw-total-return`. It returns a blocked state unless a persisted coverage-attestation record is verified, tied to an enabled official source, and covers the full requested interval. It also blocks unresolved/unverified distribution observations and NAV conflicts.

This is a scheme-level pre-tax methodology, not an investor-specific return. Taxes, exit loads and actual investor reinvestment timing are excluded. The source coverage attestation is a manual assertion and is not independently discovered from the NAV feed.

## Phase 3: scheme master metadata

The scheme master now supports lifecycle, plan, option, launch/closure and current expense-ratio metadata. The history endpoint records effective-dated observations. Only explicitly verified observations from an enabled source registered as official are promoted to current scheme fields. Verified metadata URLs are checked against the source's registered base URL. Plan/option filters now use those fields instead of guessing from scheme-name text. Unclassified schemes remain unclassified.

## Phase 4: frequency and risk controls

The Funds and Compare workspaces send a daily, weekly, monthly, quarterly or yearly sampling frequency. The service retains the first actual observation as the base and selects the last actual NAV in each succeeding calendar bucket. It does not forward-fill or interpolate. Risk metrics use the corresponding annualisation factors (252, 52, 12, 4 or 1); benchmark returns continue to align on exact sampled intervals.

## Phase 5: portfolio quality

`GET /api/v1/portfolios/{scheme_code}/quality` reports the latest snapshot's reported weight, equity weight, unresolved equity exposure and resolved equity coverage. The unresolved definition is deliberately conservative: an equity holding is unresolved only when both ISIN and canonical company entity are absent. This is a diagnostic, not proof that every resolved identifier is correct.

## Phase 6: evidence and provider safety

The distribution and metadata write paths require a registered, enabled source; verified records require an official source. If a source has a registered base URL, the submitted evidence URL host must match it. Existing event status, evidence timestamps, social retention controls and source-disabled defaults remain in place. Reddit/X still must not be enabled until provider terms, attribution and access are reviewed.

## Phase 7: evaluation

The evaluation runner adds provenance completeness, verified citation ratio, stale/future-publication counts, malformed-citation detection and unsupported-claim detection. These metrics complement routing and retrieval evaluation. They do not replace financial known-answer fixtures or human review of ambiguous source authority.

## Remaining validation gates

- Execute the bounded `mfa-audit-local --live` probes from the user's local environment and archive the output; this execution environment cannot make direct outbound provider requests.
- Register each relevant AMC/distribution source with its true source URL, authority and terms/access decision before ingesting real distributions.
- Import representative AMC disclosure fixtures and compare portfolio quality output with source statements.
- Run PostgreSQL migrations and the full CI matrix, then perform a real disposable PostgreSQL/Qdrant backup-restore drill.
- Perform a separate code review after implementation, as requested.


## API contract additions

- `GET /api/v1/audit/coverage`: table counts, NAV/benchmark date ranges, conflicts and provider-sync freshness.
- `POST/GET /api/v1/schemes/{scheme_code}/metadata-observations`: effective-dated scheme master observations.
- `POST/GET /api/v1/schemes/{scheme_code}/distributions`: versioned IDCW observations, including corrections and cancellations.
- `POST/GET /api/v1/schemes/{scheme_code}/distribution-coverage`: stored source-specific completeness attestations.
- `GET /api/v1/schemes/{scheme_code}/idcw-total-return`: reinvested IDCW index, blocked until the persisted attestation and all in-range records pass checks.
- `GET /api/v1/portfolios/{scheme_code}/quality`: holdings resolution and reported-weight coverage.

## Portfolio source-format limitation

The importer continues to accept normalized CSV/XLSX holdings and requires explicit asset classes rather than guessing them. A source-specific AMC adapter is not claimed as complete without a representative official file, its publication notes and a tested column mapping. The quality endpoint reports the unresolved equity share so these limitations are visible rather than hidden.


## Additional Phase 0–7 hardening

- `GET /api/v1/schemes/{scheme_code}/metadata-quality` reports missing catalogue fields, completeness percentage, latest source observation, verification status and observation age. Freshness bands are explicit (up to 90 days fresh, 91–180 ageing, over 180 stale); these are application review thresholds, not regulator-defined freshness guarantees.
- `GET /api/v1/portfolios/{scheme_code}/quality` reports missing holding weights, weight coverage, disclosure publication lag, effective-date age, stale/future-dated status, and quality warnings.
- The CSV/XLSX normalizer recognizes common portfolio disclosure columns (ISIN, instrument name, industry, percent to NAV, and market value in INR lakhs) while still requiring an explicit asset class.
- PDF extraction now reports malformed and password-protected files distinctly; scanned documents remain unsupported because OCR has not been implemented.
- Offline agent tests cover no-key deterministic fallback and the untrusted-document instruction boundary.


## Event correction history

The active event record remains the current view. When a manual event update or an RSS source refresh replaces an existing event state, the prior event fields and a JSON-safe evidence snapshot are appended to `market_event_revisions`. The history route is `GET /api/v1/events/{event_id}/revisions`. RSS observations continue to be stored as reported, not automatically confirmed.


### Local CSV import commands

- `mfa-import-scheme-metadata metadata.csv --source-key <registered-source-key>`
- `mfa-import-idcw distributions.csv --source-key <registered-source-key>`

Both commands accept a `source_url` column or a shared `--source-url`, default to `unverified`, check the registered source and matching URL host, validate dates/fields, and skip exact duplicate metadata rows or distribution revisions. The optional `--verification-status verified` flag is intended only after manual review against the official original notice; it additionally requires an enabled official source with a registered base URL. IDCW imports never create a coverage attestation. Column headers and use guidance are documented in the README section “Import source-attributed scheme metadata and IDCW declarations”.


### Source registry setup

Use `mfa-register-source` to create/update a local source entry with an explicit authority tier, official flag, enabled state, base URL and optional terms URL. Prefer one unique source key per AMC and keep it disabled until the source's authority, access terms and attribution requirements have been reviewed. A verified metadata or distribution import requires an enabled source explicitly registered as official and a matching base URL host.
