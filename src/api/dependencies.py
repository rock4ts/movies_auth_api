from typing import AsyncGenerator
from uuid import uuid4

import backoff
from fastapi.responses import RedirectResponse
import user_agents
from async_fastapi_jwt_auth import AuthJWT
from fastapi import HTTPException, Request, status
from fastapi.params import Depends
from redis import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, settings
from db.postgres import PostgresHelper, get_pg_helper
from db.redis import get_redis_connection
from db.repository import AsyncBaseRepository, AsyncSqlAlchemyRepository
from services.auth.yandex.schemas import YandexIdLoginRequestParams
from schemas.enums import SystemRoles
from services.auth.yandex.enums import YandexAuthRedisPrefix
from services.role import RoleService


def get_app_settings() -> Settings:
    return settings


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


def get_yandexid_login_url_params(
    request: Request,
    app_settings: Settings = Depends(get_app_settings)
) -> YandexIdLoginRequestParams:
    params_dict = {"client_id": app_settings.oauth_yandex.client_id}

    if user_agent := request.headers.get("User-Agent"):
        params_dict.update(
            {"device_name": str(user_agents.parse(user_agent)), "device_id": uuid4()}
        )
    
    return YandexIdLoginRequestParams(**params_dict)


def compile_yandexid_login_url(
    app_settings: Settings = Depends(get_app_settings),
    login_params: YandexIdLoginRequestParams = Depends(get_yandexid_login_url_params),
) -> HttpUrl:
    result_url = app_settings.oauth_yandex.auth_url
    login_params_dict = login_params.model_dump(mode="json", exclude_none=True)

    for i, kv in enumerate(login_params_dict.items()):
        k, v = kv
        if i == 0:
            result_url += f"?{k}={v}"
        else:
            result_url += f"&{k}={v}"

    return result_url


def get_yandexid_api_redirect(
    settings: Settings = Depends(get_app_settings),
    redirect_url: HttpUrl = Depends(compile_yandexid_login_url)
) -> RedirectResponse:
    return RedirectResponse(
        url=redirect_url,
        status_code=302,
        headers={"Authorization": settings.oauth_yandex.auth_header}
    )


@backoff.on_exception(backoff.expo, ConnectionError, max_time=15, raise_on_giveup=False)
async def cache_yandexid_login_params(
    login_params: YandexIdLoginRequestParams = Depends(get_yandexid_login_url_params),
    redis: Redis = Depends(get_redis_connection)
) -> bool | None:
    login_params_json = login_params.model_dump_json(exclude_none=True)
    # Время жизни кода подтверждения - 10 минут, на минуту больше даём для авторизации
    result = await redis.setex(
        f"{YandexAuthRedisPrefix.YALOGIN}:{login_params.state}", 660, login_params_json
    )

