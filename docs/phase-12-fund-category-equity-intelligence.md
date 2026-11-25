# Phase 12 — Fund, Category and Underlying Equity Intelligence

## Scope

Phase 12 adds three deterministic research surfaces on top of the existing reconciled NAV and AMC holdings-disclosure data:

1. **Category-relative fund analysis** — the selected scheme is compared only with schemes sharing its exact stored category, scheme type, plan and option. CAGR, absolute return, annualized volatility, Sharpe ratio and maximum drawdown are calculated from reconciled NAV. Optional TRI benchmark selection is supported. Peers without sufficient NAV history are explicitly excluded.
2. **Multi-fund disclosed-equity comparison** — pairwise overlap uses the sum of the lower disclosed NAV weight for each common security. If either snapshot is partial, the overlap is explicitly flagged as a lower bound. Combined exposure is an equal-weighted average across selected funds and is explicitly not represented as the user's actual portfolio allocation.
3. **Underlying-security status** — latest provider observations can be stored with price, percentage change, exchange status, fundamentals and corporate events. Quote time and fundamentals effective date are stored separately. Fund-level equity status joins those observations to the latest available AMC holdings disclosure by security key or ISIN.

## API

- `GET /api/v1/fund-intelligence/schemes/{scheme_code}/category`
  - Optional `start_date`, `end_date`, `benchmark_code` and `benchmark_source` query parameters.
- `POST /api/v1/fund-intelligence/compare`
  - JSON body: `{"scheme_codes":[10001,10002]}`; accepts 2–5 distinct schemes.
- `GET /api/v1/fund-intelligence/schemes/{scheme_code}/equity-status`
  - Optional `as_of` date. Returns disclosed equity holdings joined to latest stored market observations.
- `GET /api/v1/fund-intelligence/securities/{security_key}/market-status?isin=...`
  - Returns the latest stored observation and freshness state.
- `POST /api/v1/fund-intelligence/market-observations`
  - Ingests a timestamped provider observation. The source must already exist in `data_sources`, be enabled, and have source type `provider` or `official`.

## Market-data source integration

The application does not fabricate current prices or fundamentals and does not scrape exchange pages. Register and enable a licensed/approved market-data provider in the source registry, then ingest its timestamped observations through the market-observation contract. The API stores immutable provider observations; the latest quote is not assumed to be live merely because it is the newest stored record.

The default freshness window is 72 hours. This is a coarse data-age signal, not a trading-calendar oracle; clients must display the provider timestamp, source and exchange status. A missing observation is returned as `unavailable`, never as a zero price or healthy status. Fundamental fields are allow-listed and numeric; corporate-event records remain source-attributed provider payloads.

## Important interpretation safeguards

- Holdings are dated AMC disclosures. They are not real-time fund positions.
- Each fund may have a different holdings effective date; the API returns each date separately.
- Equity intelligence is restricted to holdings explicitly classified as `equity`; debt, cash, derivatives, REIT/InvIT and gold are not treated as shares.
- Identity matching uses exact security key or ISIN. No fuzzy name matching is used for market-price joins.
- Category rankings are descriptive cohort ranks, not future-return predictions or investment recommendations.
- NAV-only returns exclude IDCW distributions; use the existing distribution-aware analytics where an eligible and sufficiently covered total-return series is available.
- Market observations are immutable and source-attributed. Corrections should be ingested as new observations, not overwrites.

## Migration

Alembic revision: `0011_security_market_observations`, following `0010_market_event_revisions`.
