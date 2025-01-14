import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import sqlalchemy.exc as sa_exc
import uvicorn
from async_fastapi_jwt_auth.exceptions import AuthJWTException
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, ORJSONResponse
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from redis.asyncio import Redis
from sqlalchemy import select

from api.account import router as account_router
from api.auth import router as auth_router
from api.role import router as role_router
from core.config import settings
from db import postgres, redis
from models import Role, User

logger = logging.getLogger(__name__)


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
    redis.redis_client = Redis(
        host=settings.redis.host, port=settings.redis.port
    )
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


configure_tracer()
app = FastAPI(
    lifespan=lifespan,
    root_path="/auth",
)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(role_router, prefix='/role')
FastAPIInstrumentor.instrument_app(app)


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}
    )

@app.middleware('http')
async def before_request(request: Request, call_next):
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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=True,
    )
