"""Central logging configuration with safe request-correlation fields."""

import logging

from mutual_fund_agent_analysis.core.config import get_settings


class RequestLogDefaults(logging.Filter):
    """Supply safe placeholders so request fields are available on every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name in ("request_id", "method", "path", "status_code", "duration_ms"):
            if not hasattr(record, name):
                setattr(record, name, "-")
        return True


def configure_logging() -> None:
    """Configure consistent application-wide logging without request query strings."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "request_id=%(request_id)s method=%(method)s path=%(path)s "
            "status=%(status_code)s duration_ms=%(duration_ms)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestLogDefaults())
