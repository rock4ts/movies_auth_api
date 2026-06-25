import logging
from .config import settings
from opentelemetry import trace

from .request_context import get_request_id


LOG_LEVEL = "DEBUG" if settings.debug else "INFO"


def log_handled_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    logger.info("%s: exception=%s", message, type(exc).__name__)


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()

        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            record.trace_id = f"{span_context.trace_id:032x}"
            record.span_id = f"{span_context.span_id:016x}"
        else:
            record.trace_id = "-"
            record.span_id = "-"

        return True


LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - "
    "request_id=%(request_id)s trace_id=%(trace_id)s span_id=%(span_id)s - %(message)s"
)
LOG_DEFAULT_HANDLERS = [
    "console",
]

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": LOG_FORMAT},
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s request_id=%(request_id)s trace_id=%(trace_id)s span_id=%(span_id)s %(message)s",
            "use_colors": None,
        },
        "access": {
            "()": "uvicorn.logging.AccessFormatter",
            "fmt": (
                "%(levelprefix)s request_id=%(request_id)s trace_id=%(trace_id)s "
                "span_id=%(span_id)s %(client_addr)s - '%(request_line)s' %(status_code)s"
            ),
        },
    },
    "filters": {
        "trace_context": {
            "()": TraceContextFilter,
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["trace_context"],
        },
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["trace_context"],
        },
        "access": {
            "formatter": "access",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "filters": ["trace_context"],
        },
    },
    "loggers": {
        "": {
            "handlers": LOG_DEFAULT_HANDLERS,
            "level": LOG_LEVEL,
        },
        "uvicorn.error": {
            "level": LOG_LEVEL,
        },
        "uvicorn.access": {
            "handlers": ["access"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "level": LOG_LEVEL,
        "formatter": "verbose",
        "handlers": LOG_DEFAULT_HANDLERS,
    },
}
