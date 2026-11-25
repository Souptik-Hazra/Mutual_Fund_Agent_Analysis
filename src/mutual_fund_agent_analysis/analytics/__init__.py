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
    cagr,
    calendar_year_returns,
    rolling_returns,
    trailing_return,
)
from mutual_fund_agent_analysis.analytics.risk import (
    RiskMetrics,
    calculate_risk_metrics,
)
from mutual_fund_agent_analysis.analytics.series import (
    PricePoint,
    ReturnPoint,
    normalize_prices,
    period_returns,
)
from mutual_fund_agent_analysis.analytics.service import (
    FundAnalyticsReport,
    analyze_fund,
    load_benchmark_prices,
    load_fund_prices,
)

__all__ = [
    "BenchmarkMetrics",
    "DrawdownMetrics",
    "FundAnalyticsReport",
    "PricePoint",
    "ReturnPoint",
    "RiskMetrics",
    "RollingReturn",
    "absolute_return",
    "analyze_fund",
    "align_returns",
    "calculate_benchmark_metrics",
    "calculate_drawdown",
    "calculate_risk_metrics",
    "calendar_year_returns",
    "cagr",
    "load_benchmark_prices",
    "load_fund_prices",
    "normalize_prices",
    "period_returns",
    "rolling_returns",
    "trailing_return",
]
