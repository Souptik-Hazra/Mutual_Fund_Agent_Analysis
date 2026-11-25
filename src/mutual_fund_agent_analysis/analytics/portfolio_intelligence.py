"""Investor-weighted multi-fund look-through exposure analytics."""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.investor import InvestorTransaction
from mutual_fund_agent_analysis.models.nav import NavReconciliation
from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme

D = Decimal
ADDITIONS = {"purchase", "sip", "additional_purchase", "switch_in"}
DEDUCTIONS = {"redemption", "switch_out"}


def actual_portfolio_exposure(session: Session, scheme_codes: list[int]) -> dict:
    """Use ledger units x latest accepted NAV; disclose every coverage gap."""
    if not 1 <= len(scheme_codes) <= 20 or len(set(scheme_codes)) != len(scheme_codes):
        raise ValueError("Select between one and twenty distinct scheme codes.")
    schemes = {
        x.scheme_code: x
        for x in session.scalars(
            select(MutualFundScheme).where(MutualFundScheme.scheme_code.in_(scheme_codes))
        ).all()
    }
    missing = sorted(set(scheme_codes) - set(schemes))
    if missing:
        raise ValueError(f"Unknown scheme code(s): {missing}.")
    values, contexts, excluded = {}, {}, []
    for code in scheme_codes:
        txns = session.scalars(
            select(InvestorTransaction)
            .where(InvestorTransaction.scheme_code == code)
            .order_by(InvestorTransaction.transaction_date, InvestorTransaction.transaction_id)
        ).all()
        if not txns:
            excluded.append({"scheme_code": code, "reason": "No investor transactions recorded."})
            continue
        units, invalid = D("0"), False
        for item in txns:
            if item.transaction_type in ADDITIONS:
                units += D(item.units)
            elif item.transaction_type in DEDUCTIONS:
                units -= D(item.units)
            if units < 0:
                invalid = True
                break
        if invalid:
            excluded.append(
                {"scheme_code": code, "reason": "Recorded redemptions exceed accumulated units."}
            )
            continue
        if units == 0:
            values[code] = D("0")
            contexts[code] = {"units": units, "nav": None, "nav_date": None}
            continue
        nav = session.scalar(
            select(NavReconciliation)
            .where(
                NavReconciliation.scheme_code == code,
                NavReconciliation.status.in_(["single_source", "matched"]),
            )
            .order_by(NavReconciliation.nav_date.desc())
            .limit(1)
        )
        if nav is None:
            excluded.append(
                {"scheme_code": code, "reason": "No accepted NAV is available for valuation."}
            )
            continue
        values[code] = units * D(nav.canonical_nav)
        contexts[code] = {"units": units, "nav": D(nav.canonical_nav), "nav_date": nav.nav_date}
    total = sum(values.values(), D("0"))
    stocks = defaultdict(
        lambda: {
            "security_name": "",
            "isin": None,
            "sector": None,
            "funds_present": 0,
            "actual_exposure_inr": D("0"),
            "fund_exposures": [],
        }
    )
    sectors, warnings = defaultdict(lambda: D("0")), []
    for code, value in values.items():
        if value <= 0:
            continue
        snapshot = session.scalar(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.scheme_code == code,
                PortfolioSnapshot.status.in_(["complete", "partial"]),
            )
            .order_by(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.snapshot_id.desc())
            .limit(1)
        )
        if snapshot is None:
            warnings.append({"scheme_code": code, "reason": "No portfolio disclosure."})
            continue
        if snapshot.status != "complete":
            warnings.append(
                {
                    "scheme_code": code,
                    "reason": "Partial disclosure; look-through exposure is a lower bound.",
                }
            )
        holdings = session.scalars(
            select(PortfolioHolding).where(
                PortfolioHolding.snapshot_id == snapshot.snapshot_id,
                PortfolioHolding.asset_class == "equity",
                PortfolioHolding.weight_pct.is_not(None),
            )
        ).all()
        for holding in holdings:
            key = holding.isin or holding.security_key
            amount = value * D(holding.weight_pct) / D("100")
            row = stocks[key]
            row.update(
                security_name=holding.security_name, isin=holding.isin, sector=holding.sector
            )
            row["funds_present"] += 1
            row["actual_exposure_inr"] += amount
            row["fund_exposures"].append(
                {
                    "scheme_code": code,
                    "fund_value_inr": value,
                    "disclosed_weight_pct": holding.weight_pct,
                    "exposure_inr": amount,
                    "holdings_as_of": snapshot.effective_date,
                    "disclosure_status": snapshot.status,
                }
            )
            sectors[holding.sector or "Unclassified"] += amount
    items = []
    for key, row in stocks.items():
        row["actual_portfolio_weight_pct"] = (
            row["actual_exposure_inr"] / total * D("100") if total > 0 else None
        )
        items.append({"security_key": key, **row})
    items.sort(key=lambda x: x["actual_exposure_inr"], reverse=True)
    sector_rows = [
        {
            "sector": k,
            "exposure_inr": v,
            "actual_portfolio_weight_pct": v / total * D("100") if total > 0 else None,
        }
        for k, v in sectors.items()
    ]
    sector_rows.sort(key=lambda x: x["exposure_inr"], reverse=True)
    return {
        "scheme_codes": scheme_codes,
        "valuation_basis": "Investor transaction units multiplied by latest accepted reconciled NAV.",
        "total_valued_portfolio_inr": total,
        "valued_funds": [
            {
                "scheme_code": c,
                "scheme_name": schemes[c].scheme_name,
                "units": contexts[c]["units"],
                "latest_nav": contexts[c]["nav"],
                "nav_date": contexts[c]["nav_date"],
                "market_value_inr": v,
                "portfolio_weight_pct": v / total * D("100") if total > 0 else None,
            }
            for c, v in values.items()
        ],
        "excluded_funds": excluded,
        "equity_exposure": items,
        "sector_exposure": sector_rows,
        "disclosure_warnings": warnings,
        "coverage": {
            "valued_fund_count": len(values),
            "selected_fund_count": len(scheme_codes),
            "is_complete": not excluded and not warnings,
        },
        "warning": "Equity look-through uses dated AMC disclosures and investor-ledger-derived fund values. It is not a live holdings feed; missing or partial disclosures understate exposure.",
    }
