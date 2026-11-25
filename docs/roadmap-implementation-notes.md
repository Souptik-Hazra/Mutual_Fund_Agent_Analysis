# Financial Reliability Roadmap — Implementation Notes

## Implemented in the current integration package

- Exact-date monthly SIP simulation with explicit missed-installment reporting.
- Separate simulated SIP XIRR and actual investor-ledger XIRR methodologies.
- Benchmark-relative tracking error and information ratio over exact aligned intervals.
- Personal investor transaction ledger for purchases, SIPs, additions, redemptions, switches,
  dividend payouts, charges, and taxes.
- Versioned API contracts for ledger creation/listing/deletion, as-of investor returns, SIP
  simulation, and benchmark-relative active risk.
- PostgreSQL migration for the ledger, with a reversible downgrade.
- Local workspace integration for SIP simulation and investor ledger workflows.

## Financial conventions and safeguards

- SIP purchases and terminal valuation require exact-date NAV observations. Missing installment
  dates are counted as missed; no next-day NAV substitution or forward-fill is performed.
- SIP XIRR is based on hypothetical scheduled contributions and terminal value. It is not actual
  investor XIRR.
- Ledger amounts and units are positive magnitudes; transaction type determines the cash-flow
  sign. Purchases and charges are outflows; redemptions, switch-outs, and distributions are inflows.
- Investor return uses recorded realized proceeds plus current valuation of unredeemed units.
  An exact reconciled NAV is required to value an open unit balance. NAV conflicts are rejected.
- Tracking error is the sample standard deviation of active periodic returns, annualized by
  sqrt(periods_per_year). Information ratio is mean active periodic return divided by periodic
  tracking error, annualized by the same square-root factor.
- Missing, conflicting, or incomplete source data remains undefined rather than being fabricated.

## Still open; source or operational gates remain

- IDCW distribution history requires verified official ex-date, record/payment date, amount,
  plan/option, and correction disclosures before total-return calculations can be enabled.
- Scheme lifecycle, effective-dated expense-ratio observations, and benchmark mapping require
  authoritative source fields and historical fixtures.
- AMC-specific holdings adapters require actual official file layouts and fixtures per AMC.
- Portfolio unresolved-weight/coverage diagnostics and audited entity reconciliation still need
  broader integration.
- Reddit/X retention and purge verification, source rights review, and source freshness/correction
  tracking require provider-specific review before collection is enabled.
- Expanded agent evaluation needs numerical parity, evidence-quality, temporal, and adversarial
  datasets and regression thresholds.
- Local PostgreSQL/Qdrant backup, restore, recovery, dependency scanning, and upload/security
  exercises need to be run and documented on the target local environment.
- Live MFAPI, AMFI, and Nifty TRI retrieval remains separately gated from offline CI.

## Scope

The application remains a personal local research tool. This work does not add public hosting,
multi-user accounts, production authentication, cloud deployment, or autonomous trading.
