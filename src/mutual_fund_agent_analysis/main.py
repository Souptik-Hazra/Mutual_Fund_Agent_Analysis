"""FastAPI application entry point."""

import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

from mutual_fund_agent_analysis import __version__
from mutual_fund_agent_analysis.api.routes.advanced_fund_intelligence import (
    router as advanced_fund_intelligence_router,
)
from mutual_fund_agent_analysis.api.routes.assistant import router as assistant_router
from mutual_fund_agent_analysis.api.routes.financial import router as financial_router
from mutual_fund_agent_analysis.api.routes.fund_intelligence import (
    router as fund_intelligence_router,
)
from mutual_fund_agent_analysis.api.routes.funds import router as funds_router
from mutual_fund_agent_analysis.api.routes.health import router as health_router
from mutual_fund_agent_analysis.api.routes.intelligence import router as intelligence_router
from mutual_fund_agent_analysis.api.routes.market_data import router as market_data_router
from mutual_fund_agent_analysis.api.routes.research import router as research_router
from mutual_fund_agent_analysis.core.config import get_settings
from mutual_fund_agent_analysis.core.logging_config import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory used by production and tests."""
    configure_logging()
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Personal mutual fund research and market intelligence API.",
    )
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(funds_router, prefix=settings.api_v1_prefix)
    application.include_router(financial_router, prefix=settings.api_v1_prefix)
    application.include_router(fund_intelligence_router, prefix=settings.api_v1_prefix)
    application.include_router(advanced_fund_intelligence_router, prefix=settings.api_v1_prefix)
    application.include_router(market_data_router, prefix=settings.api_v1_prefix)
    application.include_router(intelligence_router, prefix=settings.api_v1_prefix)
    application.include_router(research_router, prefix=settings.api_v1_prefix)
    application.include_router(assistant_router, prefix=settings.api_v1_prefix)

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        supplied_id = request.headers.get("x-request-id", "")
        is_valid_request_id = bool(re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied_id))
        request_id = supplied_id if is_valid_request_id else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "http.request.failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "http.request.completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    return application


app = create_app()
