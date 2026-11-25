# Phases 13–16 implementation

## Phase 13 — Indian equity market data provider
- Added a Twelve Data quote adapter with explicit symbol and exchange, bounded HTTP timeout, strict timestamp parsing, finite numeric validation and normalized quote contract.
- Indian exchange access is not enabled by default. Configure an API key and independently confirm that the subscription grants NSE/BSE access and internal AI-assistant use before enabling ingestion. Exchange add-ons and licensing are account-specific.
- The adapter currently normalizes quote observations only. It does not claim that historical prices, fundamentals or corporate actions are available on the selected plan.
- Existing security observation persistence remains source-attributed and immutable. Cached observations are not live ticks.

## Phase 14 — Category benchmark intelligence
- Added effective-dated category/type/plan/option mappings.
- Mapping resolution is exact-cohort and fails closed when overlapping active mappings exist.
- No default benchmark is guessed. Add mappings only with a documented rationale and source.

## Phase 15 — Unified individual fund profile
- Added a profile endpoint composing deterministic performance/risk, category position, benchmark mapping, latest holdings disclosure and locally stored linked market events.
- Each section returns an explicit available/unavailable/ambiguous status.
- The profile carries methodology and data limitations; it is not investment advice.

## Phase 16 — Actual multi-fund portfolio look-through
- Added look-through aggregation weighted by investor-ledger units multiplied by the latest reconciled NAV.
- Stock and sector exposure are expressed in INR and as a percentage of total valued fund positions.
- Funds without ledger/NAV valuation are excluded with explicit reasons; partial/missing holdings disclosures are surfaced.
- This is distinct from equal-weighted hypothetical fund comparisons and is not a real-time holdings feed.

## Configuration and operations
- Run Alembic upgrade head after pulling this change.
- Twelve Data is not called until the account has confirmed exchange entitlements; no market data is fabricated.
- Existing local-only operation remains supported; no cloud deployment is introduced.
