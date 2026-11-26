# Fund return basis and comparison methodology

## Fund-level return basis

- **Growth options:** use the canonical reconciled NAV series. Growth NAV reflects the scheme's reinvestment option; no separate IDCW cash distribution adjustment is applied.
- **IDCW reinvestment:** use the reinvested distribution index, with each verified ex-date distribution reinvested at that ex-date NAV.
- **IDCW payout:** use the payout index, adding cumulative per-unit cash distributions to ex-distribution NAV for fixed original units. It assumes payout cash earns no interest.
- **Other or unclassified options:** report NAV-only price changes and disclose that IDCW distributions are excluded.

An IDCW total-return series is eligible only when a persisted coverage attestation is marked verified and coverage_complete, issued by an enabled official source, and covers the complete actual NAV observation interval used by the calculation. Every active distribution observation from that attested source in the interval must also be verified against an enabled official source. The existing source-host and official-source attestation requirements remain in force.

The calculation uses stored reconciled NAV observations and verified distributions. It does not infer missing distributions, forward-fill NAVs, or discover omissions independently of the attestation.

## Benchmark-relative metrics

Benchmark observations are TRI values. A benchmark comparison is allowed only when the fund return series is on a compatible total-return basis. If an IDCW scheme lacks complete verified distribution coverage:

- Fund-only NAV metrics may be returned with return_basis=nav_only_excludes_idcw.
- Alpha, beta and other benchmark-relative metrics are suppressed.
- The response includes distribution_coverage_status and benchmark_unavailable_reason.
- The active-risk endpoint rejects tracking error and information ratio requests rather than comparing NAV-only IDCW returns with TRI returns.

The benchmark basis is explicitly reported as tri whenever a comparison is calculated.

## Multi-fund comparisons and category rankings

Multi-fund comparisons reject Growth/IDCW option mixtures. IDCW funds are compared only when all selected funds share one return basis. If distribution coverage is incomplete, benchmark-relative metrics are suppressed for the entire comparison.

Category rankings retain the exact category, scheme type, plan and option cohort. Every ranked peer must share the selected fund's actual start/end dates, identical observation dates and the same return basis. Peers that cannot meet those conditions are listed as excluded with a reason; no missing observations are synthesized.

## Interpretation limits

The payout index is a scheme-level pre-tax index, not an investor-specific after-tax return. Exit loads, investor taxes, transaction timing and individual reinvestment behavior are not modeled. A verified coverage attestation is a source-backed assertion; the application does not independently prove that the source omitted no declaration.
