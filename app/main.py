import logging.config
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api import router_auth, router_role, router_user, router_yandexid
from app.api.middleware import RequestIdMiddleware

# from app.api.mock import router as mock_router
from app.core.config import settings
from app.core.logging import LOGGING_CONFIG
from app.core.tracing import configure_tracing
from app.db.helpers import (
    create_all_tables,
    create_superuser,
    drop_all_tables,
    get_or_create_default_role,
)

logging.config.dictConfig(LOGGING_CONFIG)


async def setup_for_development() -> None:
    await drop_all_tables()
    await create_all_tables()
    await create_superuser(settings.superuser_email, settings.superuser_password)
    _ = await get_or_create_default_role()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if settings.reset_db_on_startup:
        await setup_for_development()

    yield


app = FastAPI(
    lifespan=lifespan,
    root_path="/auth/api",
)
app.add_middleware(RequestIdMiddleware, header_name=settings.request_id_header)
app.include_router(router_auth, tags=["auth"])
app.include_router(router_user, prefix="/users", tags=["user"])
app.include_router(router_role, prefix="/roles", tags=["role"])
app.include_router(router_yandexid, prefix="/yandexid", tags=["yandexid"])
# app.include_router(mock_router, prefix="/mock")
configure_tracing(app)


if __name__ == "__main__":
    uvicorn.run(app="app.main:app", host="0.0.0.0", port=8000, reload=True)
