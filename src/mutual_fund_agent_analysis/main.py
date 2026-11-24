"""FastAPI application entry point."""

from fastapi import FastAPI

from mutual_fund_agent_analysis import __version__
from mutual_fund_agent_analysis.api.routes.health import router as health_router
from mutual_fund_agent_analysis.core.config import get_settings
from mutual_fund_agent_analysis.core.logging_config import configure_logging


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
    return application


app = create_app()
