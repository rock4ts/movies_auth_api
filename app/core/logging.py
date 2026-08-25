import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from opentelemetry import trace

from .config import settings
from .request_context import get_request_id

LOG_LEVEL = "DEBUG" if settings.debug else "INFO"


def log_handled_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    logger.info("%s: exception=%s", message, type(exc).__name__, exc_info=settings.debug)


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


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "service": {"name": "auth-api"},
            "log": {"level": record.levelname, "logger": record.name},
            "message": record.getMessage(),
            "process": {"pid": record.process},
            "request": {"id": getattr(record, "request_id", "-")},
            "trace": {"id": getattr(record, "trace_id", "-")},
            "span": {"id": getattr(record, "span_id", "-")},
        }
        if record.exc_info:
            payload["error"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "stack_trace": self.formatException(record.exc_info),
            }
        if record.stack_info:
            payload["stack_trace"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=False)


LOG_FORMAT = (
    "%(asctime)s - %(name)s - %(levelname)s - "
    "request_id=%(request_id)s trace_id=%(trace_id)s span_id=%(span_id)s - %(message)s"
)
LOG_DEFAULT_HANDLERS = [
    "console",
]

if settings.log_file_path:
    Path(settings.log_file_path).parent.mkdir(parents=True, exist_ok=True)
    LOG_DEFAULT_HANDLERS.append("json_file")

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": JsonFormatter},
        "verbose": {"format": LOG_FORMAT},
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": (
                "%(levelprefix)s request_id=%(request_id)s "
                "trace_id=%(trace_id)s span_id=%(span_id)s %(message)s"
            ),
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
        **(
            {
                "json_file": {
                    "class": "concurrent_log_handler.ConcurrentRotatingFileHandler",
                    "filename": settings.log_file_path,
                    "maxBytes": settings.log_max_bytes,
                    "backupCount": settings.log_backup_count,
                    "encoding": "utf-8",
                    "formatter": "json",
                    "filters": ["trace_context"],
                }
            }
            if settings.log_file_path
            else {}
        ),
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
            "handlers": [
                "access",
                *(["json_file"] if settings.log_file_path else []),
            ],
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
