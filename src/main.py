from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from redis.asyncio import Redis
from async_fastapi_jwt_auth.exceptions import AuthJWTException
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, ORJSONResponse

from api.account import router as account_router
from api.auth import router as auth_router
from api.role import router as role_router
from core.config import settings
from db import redis, postgres


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # startup
    redis.redis_client = Redis(
        host=settings.redis.url, port=settings.redis.port
    )
    postgres.pg_helper = postgres.PostgresHelper(
        url=str(settings.db.url),
        echo=settings.db.echo,
        echo_pool=settings.db.echo_pool,
        pool_size=settings.db.pool_size,
        max_overflow=settings.db.max_overflow,
    )
    yield
    # shutdown
    await postgres.pg_helper.dispose()


app = FastAPI(
    lifespan=lifespan,
    root_path="/auth",
)
app.include_router(auth_router)
app.include_router(account_router)
app.include_router(role_router, prefix='/role')


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message}
    )

@app.middleware('http')
async def before_request(request: Request, call_next):
    response = await call_next(request)
    request_id = request.headers.get('X-Request-Id')
    if not request_id:
        return ORJSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={'detail': 'X-Request-Id is required'})
    return response 


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=True,
    )
