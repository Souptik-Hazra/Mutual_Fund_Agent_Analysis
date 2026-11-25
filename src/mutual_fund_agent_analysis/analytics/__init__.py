"""Deterministic mutual-fund performance and risk analytics."""

from mutual_fund_agent_analysis.analytics.benchmark import (
    BenchmarkMetrics,
    align_returns,
    calculate_benchmark_metrics,
)
from mutual_fund_agent_analysis.analytics.active_risk import (
    ActiveRiskMetrics,
    calculate_active_risk_metrics,
)
from mutual_fund_agent_analysis.analytics.investor import (
    InvestorReturnReport,
    InvestorTransactionInput,
    calculate_investor_returns,
)
from mutual_fund_agent_analysis.analytics.sip import (
    SipInstallment,
    SipSimulation,
    simulate_monthly_sip,
)
from mutual_fund_agent_analysis.analytics.cashflows import (
    CashFlow,
    normalize_cash_flows,
    xirr,
    xnpv,
)
from mutual_fund_agent_analysis.analytics.coverage import ReturnCoverage, assess_return_coverage
from mutual_fund_agent_analysis.analytics.drawdown import DrawdownMetrics, calculate_drawdown
from mutual_fund_agent_analysis.analytics.returns import (
    RollingReturn,
    TrailingReturn,
    absolute_return,
    cagr,
    calendar_year_returns,
    rolling_returns,
    trailing_return,
    trailing_return_details,
)
from mutual_fund_agent_analysis.analytics.risk import (
    RiskMetrics,
    calculate_risk_metrics,
)
from mutual_fund_agent_analysis.analytics.series import (
    PricePoint,
    ReturnPoint,
    normalize_prices,
    normalize_returns,
    period_returns,
)
from mutual_fund_agent_analysis.analytics.service import (
    FundAnalyticsReport,
    FundComparisonReport,
    analyze_fund,
    compare_funds,
    load_benchmark_prices,
    load_fund_prices,
)

__all__ = [
    "ActiveRiskMetrics",
    "InvestorReturnReport",
    "InvestorTransactionInput",
    "SipInstallment",
    "SipSimulation",
    "calculate_active_risk_metrics",
    "calculate_investor_returns",
    "simulate_monthly_sip",
    "CashFlow",
    "BenchmarkMetrics",
    "DrawdownMetrics",
    "FundAnalyticsReport",
    "FundComparisonReport",
    "PricePoint",
    "ReturnCoverage",
    "ReturnPoint",
    "RiskMetrics",
    "RollingReturn",
    "TrailingReturn",
    "absolute_return",
    "analyze_fund",
    "align_returns",
    "assess_return_coverage",
    "calculate_benchmark_metrics",
    "calculate_drawdown",
    "calculate_risk_metrics",
    "calendar_year_returns",
    "cagr",
    "compare_funds",
    "load_benchmark_prices",
    "load_fund_prices",
    "normalize_cash_flows",
    "normalize_prices",
    "normalize_returns",
    "period_returns",
    "rolling_returns",
    "trailing_return",
    "trailing_return_details",
    "xirr",
    "xnpv",
]
