"""Investor-weighted multi-fund look-through exposure analytics."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.models.intelligence import DataSource, EvidenceRecord
from mutual_fund_agent_analysis.models.investor import InvestorTransaction
from mutual_fund_agent_analysis.models.nav_reconciliation import NavReconciliation
from mutual_fund_agent_analysis.models.research import PortfolioHolding, PortfolioSnapshot
from mutual_fund_agent_analysis.models.scheme import MutualFundScheme

D = Decimal
ADDITIONS = {"purchase", "sip", "additional_purchase", "switch_in"}
DEDUCTIONS = {"redemption", "switch_out"}
ACCEPTED_NAV_STATUSES = {"single_source", "matched"}


def actual_portfolio_exposure(
    session: Session, scheme_codes: list[int], as_of_date: date | None = None
) -> dict:
    """Value dated investor units and look through the latest eligible disclosure.

    The newest NAV row on or before the valuation date is inspected before its
    status is checked. A conflict therefore blocks valuation instead of causing
    an unnoticed fallback to an older accepted NAV.
    """
    if not 1 <= len(scheme_codes) <= 20 or len(set(scheme_codes)) != len(scheme_codes):
        raise ValueError("Select between one and twenty distinct scheme codes.")
    if as_of_date is None:
        as_of_date = date.today()
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a calendar date.")

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
    data_quality_warnings = []
    for code in scheme_codes:
        txns = session.scalars(
            select(InvestorTransaction)
            .where(
                InvestorTransaction.scheme_code == code,
                InvestorTransaction.transaction_date <= as_of_date,
            )
            .order_by(InvestorTransaction.transaction_date, InvestorTransaction.transaction_id)
        ).all()
        if not txns:
            excluded.append(
                {
                    "scheme_code": code,
                    "reason": f"No investor transactions on or before {as_of_date}.",
                }
            )
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
                {
                    "scheme_code": code,
                    "reason": (
                        "Recorded redemptions exceed accumulated units as of the valuation date."
                    ),
                }
            )
            continue
        if units == 0:
            excluded.append(
                {
                    "scheme_code": code,
                    "reason": (
                        "No remaining units after recorded redemptions and switches as of the "
                        "valuation date."
                    ),
                }
            )
            continue

        # Do not filter by status before choosing the newest row: a conflict on
        # that date must prevent an implicit fallback to an older accepted NAV.
        nav = session.scalar(
            select(NavReconciliation)
            .where(
                NavReconciliation.scheme_code == code,
                NavReconciliation.nav_date <= as_of_date,
            )
            .order_by(NavReconciliation.nav_date.desc())
            .limit(1)
        )
        if nav is None:
            excluded.append(
                {
                    "scheme_code": code,
                    "reason": f"No reconciled NAV exists on or before {as_of_date}.",
                }
            )
            continue
        if nav.status == "conflict":
            reason = (
                f"Latest NAV on or before {as_of_date} is conflicted ({nav.nav_date}); "
                "valuation is blocked rather than falling back to an older NAV."
            )
            excluded.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "nav_conflict", "reason": reason}
            )
            continue
        if nav.status not in ACCEPTED_NAV_STATUSES or nav.canonical_nav is None:
            reason = (
                f"Latest NAV on or before {as_of_date} ({nav.nav_date}) is not accepted "
                "for valuation."
            )
            excluded.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "nav_unaccepted", "reason": reason}
            )
            continue
        nav_value = D(nav.canonical_nav)
        if not nav_value.is_finite() or nav_value <= 0:
            reason = f"Latest accepted NAV on {nav.nav_date} is not a positive finite value."
            excluded.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "invalid_nav", "reason": reason}
            )
            continue

        values[code] = units * nav_value
        contexts[code] = {
            "units": units,
            "nav": nav_value,
            "nav_date": nav.nav_date,
            "nav_status": nav.status,
            "valuation_age_days": (as_of_date - nav.nav_date).days,
            "nav_source_key": nav.canonical_source,
            "nav_retrieved_at": nav.evaluated_at,
        }

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
    lookthrough_value = D("0")
    holdings_fund_codes = set()
    for code, value in values.items():
        if value <= 0:
            continue
        snapshot = session.scalar(
            select(PortfolioSnapshot)
            .join(DataSource, DataSource.source_key == PortfolioSnapshot.source_key)
            .where(
                PortfolioSnapshot.scheme_code == code,
                PortfolioSnapshot.status.in_(["complete", "partial"]),
                PortfolioSnapshot.effective_date <= as_of_date,
                DataSource.enabled.is_(True),
                DataSource.is_official.is_(True),
                DataSource.source_type == "official",
            )
            .order_by(PortfolioSnapshot.effective_date.desc(), PortfolioSnapshot.snapshot_id.desc())
            .limit(1)
        )
        if snapshot is None:
            reason = (
                f"No complete or partial holdings disclosure effective on or before {as_of_date}."
            )
            warnings.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "missing_holdings", "reason": reason}
            )
            continue

        holdings_fund_codes.add(code)
        source = session.get(DataSource, snapshot.source_key)
        evidence = (
            session.get(EvidenceRecord, snapshot.evidence_id) if snapshot.evidence_id else None
        )
        if (
            source is None
            or not source.enabled
            or not source.is_official
            or source.source_type != "official"
        ):
            reason = "The holdings source is not an enabled registered official source."
            warnings.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "untrusted_holdings_source", "reason": reason}
            )
            continue
        if evidence is None or evidence.verification_status != "verified":
            reason = "The official-source holdings disclosure has not been independently verified."
            warnings.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "unverified_holdings_evidence", "reason": reason}
            )
        holdings = session.scalars(
            select(PortfolioHolding).where(PortfolioHolding.snapshot_id == snapshot.snapshot_id)
        ).all()
        missing_weight_count = sum(1 for holding in holdings if holding.weight_pct is None)
        disclosed_weight_total = sum(
            (D(holding.weight_pct) for holding in holdings if holding.weight_pct is not None),
            D("0"),
        )
        weight_complete = missing_weight_count == 0 and D("99") <= disclosed_weight_total <= D(
            "101"
        )
        contexts[code].update(
            holdings_snapshot_id=snapshot.snapshot_id,
            holdings_as_of=snapshot.effective_date,
            holdings_source_key=snapshot.source_key,
            holdings_url=(
                evidence.canonical_url if evidence else (source.base_url if source else None)
            ),
            holdings_retrieved_at=evidence.retrieved_at if evidence else snapshot.retrieved_at,
            holdings_verification_status=evidence.verification_status if evidence else "unverified",
        )
        if snapshot.status == "complete" and not weight_complete:
            reason = (
                f"Complete disclosure effective {snapshot.effective_date} has "
                f"{missing_weight_count} holding(s) without weights and total disclosed "
                f"weight {disclosed_weight_total}%; look-through coverage is incomplete."
            )
            warnings.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "missing_holding_weights", "reason": reason}
            )
        if (
            snapshot.status == "complete"
            and weight_complete
            and evidence is not None
            and evidence.verification_status == "verified"
        ):
            lookthrough_value += value
        if snapshot.status != "complete":
            reason = (
                f"Holdings disclosure effective {snapshot.effective_date} is partial; "
                "look-through exposure is a lower bound."
            )
            warnings.append({"scheme_code": code, "reason": reason})
            data_quality_warnings.append(
                {"scheme_code": code, "type": "partial_holdings", "reason": reason}
            )

        for holding in holdings:
            if holding.asset_class != "equity" or holding.weight_pct is None:
                continue
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
        "as_of_date": as_of_date,
        "valuation_basis": (
            "Investor transaction units on or before as_of_date multiplied by the latest "
            "accepted reconciled NAV on or before as_of_date; a latest NAV conflict "
            "blocks valuation."
        ),
        "total_valued_portfolio_inr": total,
        "valued_funds": [
            {
                "scheme_code": c,
                "scheme_name": schemes[c].scheme_name,
                "units": contexts[c]["units"],
                "latest_nav": contexts[c]["nav"],
                "nav_date": contexts[c]["nav_date"],
                "nav_status": contexts[c]["nav_status"],
                "valuation_age_days": contexts[c]["valuation_age_days"],
                "nav_source_key": contexts[c]["nav_source_key"],
                "nav_retrieved_at": contexts[c]["nav_retrieved_at"],
                "holdings_snapshot_id": contexts[c].get("holdings_snapshot_id"),
                "holdings_as_of": contexts[c].get("holdings_as_of"),
                "holdings_source_key": contexts[c].get("holdings_source_key"),
                "holdings_url": contexts[c].get("holdings_url"),
                "holdings_retrieved_at": contexts[c].get("holdings_retrieved_at"),
                "holdings_verification_status": contexts[c].get(
                    "holdings_verification_status", "unverified"
                ),
                "market_value_inr": v,
                "portfolio_weight_pct": v / total * D("100") if total > 0 else None,
            }
            for c, v in values.items()
            if contexts[c]["units"] > 0 and v > 0
        ],
        "excluded_funds": excluded,
        "equity_exposure": items,
        "sector_exposure": sector_rows,
        "disclosure_warnings": warnings,
        "data_quality_warnings": data_quality_warnings,
        "coverage": {
            "valued_fund_count": sum(1 for value in values.values() if value > 0),
            "selected_fund_count": len(scheme_codes),
            "holdings_fund_count": len(holdings_fund_codes),
            "lookthrough_covered_value_inr": lookthrough_value,
            "lookthrough_coverage_pct": (
                lookthrough_value / total * D("100") if total > 0 else D("0")
            ),
            "is_complete": not excluded and not warnings and not data_quality_warnings,
        },
        "warning": (
            "Equity look-through uses the latest eligible dated AMC disclosures and "
            "investor-ledger-derived fund values. It is not a live holdings feed; missing "
            "or partial disclosures understate exposure. NAV dates can differ by scheme."
        ),
    }
