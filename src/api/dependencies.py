from typing import AsyncGenerator

import backoff
from async_fastapi_jwt_auth import AuthJWT
from fastapi import HTTPException, status
from fastapi.params import Depends
from redis import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from db.postgres import PostgresHelper, get_pg_helper
from db.redis import get_redis_connection
from db.repository import AsyncBaseRepository, AsyncSqlAlchemyRepository
from schemas.enums import SystemRoles
from services.role import RoleService


def get_role_service() -> RoleService:
    return RoleService


async def get_session(
    pg_helper: PostgresHelper = Depends(get_pg_helper),
) -> AsyncGenerator[AsyncSession, None]:
    async with pg_helper.session_factory() as session:
        yield session


async def get_sqlalchemy_repository(
    pg_helper: PostgresHelper = Depends(get_pg_helper),
) -> AsyncGenerator[AsyncBaseRepository, None]:
    async with pg_helper.session_factory() as session:
        yield AsyncSqlAlchemyRepository(session)


async def get_token_сlaims(authjwt: AuthJWT = Depends()) -> dict:
    token_claims = await authjwt.get_raw_jwt()
    if not token_claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token required"
        )
    return token_claims


@backoff.on_exception(backoff.expo, ConnectionError, max_time=15)
async def check_invalid_token(
    token_claims: dict = Depends(get_token_сlaims),
    redis_client: Redis = Depends(get_redis_connection),
) -> bool:
    jti = token_claims["jti"]
    res = await redis_client.get(f"blacklist:{jti}")

    if res is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid"
        )


async def check_superuser(
    token_claims: dict = Depends(get_token_сlaims),
) -> None:
    user_role = token_claims.get("roles")

    if user_role != SystemRoles.SUPERUSER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Superuser required",
        )
