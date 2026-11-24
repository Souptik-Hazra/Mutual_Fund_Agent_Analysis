"""Central logging configuration."""
import logging

from mutual_fund_agent_analysis.core.config import get_settings


def configure_logging() -> None:
    """Configure consistent application-wide log formatting."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
