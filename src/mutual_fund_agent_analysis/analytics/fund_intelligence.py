"""Category-relative fund analysis and multi-fund disclosed-equity exposure."""

from collections import defaultdict
from dataclasses import asdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.analytics.service import analyze_fund
from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme


def analyze_category_peers(
    session: Session,
    scheme_code: int,
    start_date: date | None = None,
    end_date: date | None = None,
    max_peers: int = 100,
    benchmark_code: str | None = None,
    benchmark_source: str = "niftyindices",
) -> dict:
    """Rank funds only against same-category, same-plan and same-option peers."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be on or before end_date.")
    selected = session.get(MutualFundScheme, scheme_code)
    if selected is None:
        raise ValueError("Scheme not found in the local catalogue.")
    if not selected.scheme_category:
        raise ValueError("Scheme category is missing; category-relative ranking is unavailable.")
    filters = [
        MutualFundScheme.scheme_category == selected.scheme_category,
        MutualFundScheme.plan_type == selected.plan_type,
        MutualFundScheme.option_type == selected.option_type,
    ]
    if selected.scheme_type:
        filters.append(MutualFundScheme.scheme_type == selected.scheme_type)
    peers = session.scalars(
        select(MutualFundScheme)
        .where(*filters)
        .order_by(MutualFundScheme.scheme_name, MutualFundScheme.scheme_code)
        .limit(max_peers)
    ).all()
    ranked = []
    excluded = []
    for peer in peers:
        try:
            report = analyze_fund(
                session,
                peer.scheme_code,
                benchmark_code=benchmark_code,
                start_date=start_date,
                end_date=end_date,
                benchmark_source=benchmark_source,
            )
        except ValueError as exc:
            excluded.append({"scheme_code": peer.scheme_code, "reason": str(exc)})
            continue
        ranked.append(
            {
                "scheme_code": peer.scheme_code,
                "scheme_name": peer.scheme_name,
                "fund_house": peer.fund_house,
                "category": peer.scheme_category,
                "cagr": report.cagr,
                "absolute_return": report.absolute_return,
                "annualized_volatility": report.risk.annualized_volatility,
                "sharpe_ratio": report.risk.sharpe_ratio,
                "maximum_drawdown": report.drawdown.maximum_drawdown,
                "benchmark": asdict(report.benchmark) if report.benchmark else None,
                "observation_count": report.observation_count,
                "start_date": report.start_date,
                "end_date": report.end_date,
            }
        )
    if not any(row["scheme_code"] == scheme_code for row in ranked):
        raise ValueError(
            "Selected scheme has insufficient reconciled NAV history for peer analysis."
        )
    for metric in ("cagr", "sharpe_ratio"):
        valid = sorted(
            (row for row in ranked if row[metric] is not None),
            key=lambda row: row[metric],
            reverse=True,
        )
        for rank, row in enumerate(valid, start=1):
            row[f"{metric}_rank"] = rank
            row[f"{metric}_percentile"] = (
                Decimal(len(valid) - rank + 1) / Decimal(len(valid)) * Decimal("100")
            )
    ranked.sort(key=lambda row: (row["cagr"] is None, -(row["cagr"] or Decimal("0"))))
    selected_result = next(row for row in ranked if row["scheme_code"] == scheme_code)
    return {
        "scheme_code": scheme_code,
        "category": selected.scheme_category,
        "peer_definition": {
            "category": selected.scheme_category,
            "scheme_type": selected.scheme_type,
            "plan_type": selected.plan_type,
            "option_type": selected.option_type,
        },
        "peer_count": len(ranked),
        "excluded_peer_count": len(excluded),
        "benchmark_code": benchmark_code,
        "benchmark_source": benchmark_source if benchmark_code else None,
        "selected_fund": selected_result,
        "peers": ranked,
        "excluded_peers": excluded,
        "methodology": (
            "Exact local category/type/plan/option cohort. Metrics use reconciled NAV-only "
            "returns; IDCW distributions are excluded. Peers without sufficient NAV history "
            "are excluded and listed. Ranks are descriptive, not recommendations."
        ),
    }


def compare_disclosed_equity(
    session: Session,
    scheme_codes: list[int],
) -> dict:
    """Compare latest disclosed equity weights; do not imply these are live holdings."""
    if not 2 <= len(scheme_codes) <= 5 or len(set(scheme_codes)) != len(scheme_codes):
        raise ValueError("Select between two and five distinct schemes.")
    schemes = {
        row.scheme_code: row
        for row in session.scalars(
            select(MutualFundScheme).where(MutualFundScheme.scheme_code.in_(scheme_codes))
        ).all()
    }
    missing = sorted(set(scheme_codes) - set(schemes))
    if missing:
        raise ValueError(f"Unknown scheme code(s): {missing}.")
    snapshots = {}
    holdings_by_fund = {}
    for code in scheme_codes:
        snapshot = session.scalars(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.scheme_code == code,
                PortfolioSnapshot.status.in_(["complete", "partial"]),
            )
            .order_by(
                PortfolioSnapshot.effective_date.desc(),
                PortfolioSnapshot.retrieved_at.desc(),
            )
            .limit(1)
        ).first()
        if snapshot is None:
            raise ValueError(f"No portfolio disclosure is available for scheme {code}.")
        snapshots[code] = snapshot
        rows = session.scalars(
            select(PortfolioHolding).where(
                PortfolioHolding.snapshot_id == snapshot.snapshot_id,
                PortfolioHolding.asset_class == "equity",
            )
        ).all()
        holdings_by_fund[code] = {
            row.isin or row.security_key: row for row in rows if row.weight_pct is not None
        }
    pairwise = []
    for index, left_code in enumerate(scheme_codes):
        for right_code in scheme_codes[index + 1 :]:
            left = holdings_by_fund[left_code]
            right = holdings_by_fund[right_code]
            common = sorted(set(left) & set(right))
            overlap = sum(
                (
                    min(Decimal(left[key].weight_pct), Decimal(right[key].weight_pct))
                    for key in common
                ),
                Decimal("0"),
            )
            pairwise.append(
                {
                    "scheme_a": left_code,
                    "scheme_b": right_code,
                    "overlap_pct": overlap,
                    "common_security_count": len(common),
                    "common_securities": [
                        {
                            "security_key": key,
                            "security_name": left[key].security_name,
                            "weight_a_pct": left[key].weight_pct,
                            "weight_b_pct": right[key].weight_pct,
                        }
                        for key in common
                    ],
                }
            )
    aggregate = defaultdict(
        lambda: {
            "name": "",
            "funds_present": 0,
            "equal_weight_exposure_pct": Decimal("0"),
        }
    )
    for code in scheme_codes:
        for key, holding in holdings_by_fund[code].items():
            item = aggregate[key]
            item["name"] = holding.security_name
            item["funds_present"] += 1
            item["equal_weight_exposure_pct"] += Decimal(holding.weight_pct) / Decimal(
                len(scheme_codes)
            )
    exposure = [{"security_key": key, **value} for key, value in aggregate.items()]
    exposure.sort(key=lambda row: row["equal_weight_exposure_pct"], reverse=True)
    return {
        "scheme_codes": scheme_codes,
        "funds": [
            {
                "scheme_code": code,
                "scheme_name": schemes[code].scheme_name,
                "snapshot_id": snapshots[code].snapshot_id,
                "holdings_as_of": snapshots[code].effective_date,
                "snapshot_status": snapshots[code].status,
                "equity_positions_with_weights": len(holdings_by_fund[code]),
            }
            for code in scheme_codes
        ],
        "pairwise_overlap": pairwise,
        "aggregated_equity_exposure": exposure,
        "aggregation_basis": (
            "Equal allocation to each selected fund; not the user's actual portfolio weights."
        ),
        "disclosure_warning": (
            "Holdings are the latest available AMC disclosures, not real-time positions. "
            "Different funds may have different disclosure dates. Securities without reported "
            "weights are excluded from weighted overlap and aggregate exposure."
        ),
    }
