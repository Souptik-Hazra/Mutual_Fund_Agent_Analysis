# Financial Reliability Roadmap — Implementation Notes

## Delivered in this work package

- Deterministic monthly SIP simulation over exact-date NAV observations.
- Explicit missed-installment reporting when a scheduled-date NAV is absent.
- Simulated invested capital, units, valuation, absolute gain, XIRR, and schedule coverage.
- Benchmark-relative tracking error and information ratio using exact interval alignment.

## Remaining integration and source-dependent work

- Persisted investor transaction ledger, transaction imports, API/UI workflows, folio references,
  realized proceeds, and actual investor XIRR remain distinct from the SIP simulator.
- IDCW calculations require verified ex-date, record/payment-date, amount, plan/option, and
  correction data. Distribution history must not be synthesized.
- Scheme lifecycle and expense-ratio history require authoritative, effective-dated source data.
- AMC-specific holdings adapters require verified official file formats and parsing fixtures.
- Portfolio quality indicators, evidence retention/purge verification, expanded evaluation data,
  and backup/restore/security exercises remain to be integrated and executed.
- CI, migrations, provider retrieval, and frontend contract checks must run before Phase 0 can
  be marked complete.

## Calculation conventions

- SIP purchases and terminal valuation require exact NAV dates. Missing installment dates are
  counted as missed; no next-day NAV substitution or forward-fill is performed.
- SIP XIRR is based on simulated contributions and terminal value; it is not actual investor XIRR.
- Tracking error is sample standard deviation of active periodic returns, annualized by
  sqrt(periods_per_year). Information ratio is mean active periodic return divided by periodic
  tracking error, annualized by the same square-root factor.
