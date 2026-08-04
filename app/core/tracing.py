import logging

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_OFF,
    ALWAYS_ON,
    ParentBased,
    Sampler,
    TraceIdRatioBased,
)

from app.core.config import tracing_settings

logger = logging.getLogger(__name__)

_tracing_configured = False
_clients_instrumented = False


def configure_tracing(app: FastAPI) -> None:
    if not tracing_settings.enabled:
        logger.info("Tracing is disabled")
        return

    _configure_tracer_provider()
    _instrument_clients()
    _instrument_fastapi(app)


def _configure_tracer_provider() -> None:
    global _tracing_configured

    if _tracing_configured:
        return

    provider = TracerProvider(
        resource=Resource.create({"service.name": tracing_settings.service_name}),
        sampler=_build_sampler(),
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=tracing_settings.otlp_endpoint,
                insecure=tracing_settings.otlp_insecure,
            )
        )
    )
    trace.set_tracer_provider(provider)
    _tracing_configured = True


def _build_sampler() -> Sampler:
    match tracing_settings.traces_sampler:
        case "parentbased_traceidratio":
            return ParentBased(root=TraceIdRatioBased(tracing_settings.traces_sampler_arg))
        case "traceidratio":
            return TraceIdRatioBased(tracing_settings.traces_sampler_arg)
        case "always_on":
            return ALWAYS_ON
        case "always_off":
            return ALWAYS_OFF
        case _:
            return ParentBased(root=TraceIdRatioBased(tracing_settings.traces_sampler_arg))


def _instrument_clients() -> None:
    global _clients_instrumented

    if _clients_instrumented:
        return

    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from app.db.clients import engine

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    if tracing_settings.redis_capture_statement:
        RedisInstrumentor().instrument()
    else:
        RedisInstrumentor().instrument(
            request_hook=_redis_request_hook_without_statement,
        )
    _clients_instrumented = True


def _instrument_fastapi(app: FastAPI) -> None:
    if getattr(app.state, "tracing_instrumented", False):
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    app.state.tracing_instrumented = True


def _redis_request_hook_without_statement(span, _instance, _args, _kwargs) -> None:
    if span.is_recording():
        span.set_attribute("db.statement", "")
