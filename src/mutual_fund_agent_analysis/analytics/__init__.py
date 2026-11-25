"""Deterministic mutual-fund performance and risk analytics."""

from mutual_fund_agent_analysis.analytics.benchmark import (
    BenchmarkMetrics,
    align_returns,
    calculate_benchmark_metrics,
)
from mutual_fund_agent_analysis.analytics.drawdown import DrawdownMetrics, calculate_drawdown
from mutual_fund_agent_analysis.analytics.returns import (
    RollingReturn,
    absolute_return,
    calendar_year_returns,
    cagr,
    rolling_returns,
    trailing_return,
)
from mutual_fund_agent_analysis.analytics.risk import (
    RiskMetrics,
    calculate_risk_metrics,
)
from mutual_fund_agent_analysis.analytics.service import (\n    FundAnalyticsReport,\n    analyze_fund,\n    load_benchmark_prices,\n    load_fund_prices,\n)\nfrom mutual_fund_agent_analysis.analytics.series import (
    PricePoint,
    ReturnPoint,
    normalize_prices,
    period_returns,
)

__all__ = [
    "BenchmarkMetrics",
    "DrawdownMetrics",\n    "FundAnalyticsReport",
    "PricePoint",
    "ReturnPoint",
    "RiskMetrics",
    "RollingReturn",
    "absolute_return",\n    "analyze_fund",
    "align_returns",
    "calculate_benchmark_metrics",
    "calculate_drawdown",
    "calculate_risk_metrics",
    "calendar_year_returns",
    "cagr",
    "load_benchmark_prices",\n    "load_fund_prices",\n    "normalize_prices",
    "period_returns",
    "rolling_returns",
    "trailing_return",
]
