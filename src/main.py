import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sqlalchemy.exc as sa_exc
import uvicorn
from async_fastapi_jwt_auth.exceptions import AuthJWTException
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from redis.asyncio import Redis
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from api.account import router as account_router
from api.auth import router as auth_router
from api.role import router as role_router
from core.config import settings
from db import postgres, redis
from models import Role, User

logger = logging.getLogger(__name__)


def configure_tracer() -> None:
    trace.set_tracer_provider(TracerProvider())
    otlp_exporter = OTLPSpanExporter(
        endpoint=f"http://{settings.jaeger.host}:{settings.jaeger.port}"
    )
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )
    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(ConsoleSpanExporter())
    )


async def trace_request(request: Request, call_next) -> None:
    client_ip = request.headers.get('X-Real-IP', '').lower()
    is_local = client_ip in {'localhost', '127.0.0.1', '', None}
    request_id = request.headers.get('X-Request-Id', 'unknown')

    # Не используем трассировкy локальных запросов
    if not is_local and not request_id:
        return ORJSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={'detail': 'X-Request-Id is required'}
        )

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(f"{request.method} {request.url.path}") as span:
        span.set_attribute("http.request_id", request_id)
        return await call_next(request)


def handle_authjwt_exception(request: Request, exc: AuthJWTException) -> None:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}
    )


async def create_superuser(pg_helper: postgres.PostgresHelper) -> None:
    async with pg_helper.session_factory() as session:
        role_q = await session.execute(
            select(Role).where(Role.title == settings.superuser.role_title)
        )
        superuser_role = role_q.scalars().first()

        if superuser_role is None:
            superuser_role = Role(
                title=settings.superuser.role_title,
                system_role=True
            )
        superuser = User(
            email=settings.superuser.email,
            first_name=settings.superuser.first_name,
            last_name=settings.superuser.last_name,
            role=superuser_role
        )
        superuser.set_password(settings.superuser.password)
        session.add(superuser)
        try:
            await session.commit()
        except sa_exc.IntegrityError as e:
            logger.error(str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    redis.redis_client = Redis(host=settings.redis.host, port=settings.redis.port)
    await FastAPILimiter.init(redis.redis_client)

    postgres.pg_helper = postgres.PostgresHelper(
        url=str(settings.db.url),
        echo=settings.db.echo,
        echo_pool=settings.db.echo_pool,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
    )
    await create_superuser(postgres.pg_helper)

    yield

    # shutdown
    await postgres.pg_helper.dispose()


app = FastAPI(
    lifespan=lifespan,
    root_path="/auth",
    dependencies=[Depends(RateLimiter(times=5, seconds=5)),]
)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(role_router, prefix='/role')
app.add_exception_handler(AuthJWTException, handle_authjwt_exception)

if settings.jaeger.enable is True:
    configure_tracer()
    app.add_middleware(BaseHTTPMiddleware, trace_request)
    FastAPIInstrumentor.instrument_app(app)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=True,
    )
