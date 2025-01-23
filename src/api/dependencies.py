from typing import AsyncGenerator
from uuid import uuid4

import backoff
from fastapi.responses import RedirectResponse
import httpx
from pydantic import UUID4, BaseModel, ValidationError
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
from services.oauth.yandex.schemas import (
    HttpRequestComponents,
    YandexIdLoginRequestParams,
    YandexIdTokenRequestData,
    YandexIdUserRequestParams
)
from schemas.enums import OAuthProviders, SystemRoles
from services.oauth.yandex.enums import YandexAuthRedisPrefix
from services.role import RoleService
from .exceptions import Http400, Http500


def get_app_settings() -> Settings:
    return settings


def get_role_service() -> RoleService:
    return RoleService


async def get_http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient() as http_client:
        yield http_client


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


def get_oauth_login_params(
    provider: str,
    request: Request,
    app_settings: Settings = Depends(get_app_settings)
) -> BaseModel:
    if provider == OAuthProviders.YANDEX:
        return get_yandexid_login_params(
            app_settings.oauth_yandex.client_id,
            request.headers.get("User-Agent")
        )


def get_oauth_login_cache_key(
    provider: str,
    oauth_login_params: BaseModel = Depends(get_oauth_login_params)
) -> str:
    if provider == OAuthProviders.YANDEX:
        return f"{YandexAuthRedisPrefix.YALOGIN}:{oauth_login_params.state}"


def get_oauth_login_url(
    provider: str,
    login_params: BaseModel | None = Depends(get_oauth_login_params),
    settings: Settings = Depends(get_app_settings)
) -> str:
    if provider == OAuthProviders.YANDEX:
        result_url = settings.oauth_yandex.auth_url

    if login_params is None:
        return result_url

    login_params_dict = login_params.model_dump(mode="json", exclude_none=True)
    for i, kv in enumerate(login_params_dict.items()):
        k, v = kv
        if i == 0:
            result_url += f"?{k}={v}"
        else:
            result_url += f"&{k}={v}"

    return result_url 


def get_yandexid_login_params(
    client_id: str,
    user_agent: str | None = None
) -> YandexIdLoginRequestParams:
    params_dict = {"client_id": client_id}

    if user_agent:
        params_dict.update(
            {"device_name": str(user_agents.parse(user_agent)), "device_id": uuid4()}
        )
    
    return YandexIdLoginRequestParams(**params_dict)


def get_oauth_login_redirect(
    provider: str,
    redirect_url: str = Depends(get_oauth_login_url),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    if provider == OAuthProviders.YANDEX:
        return RedirectResponse(
            url=redirect_url,
            status_code=302,
            headers={"Authorization": settings.oauth_yandex.auth_header}
        )


@backoff.on_exception(backoff.expo, ConnectionError, max_time=15, raise_on_giveup=False)
async def cache_oauth_login_params(
    cache_key: str = Depends(get_oauth_login_cache_key),
    oauth_login_params: BaseModel = Depends(get_oauth_login_params),
    redis: Redis = Depends(get_redis_connection)
) -> None:
    login_params_json = oauth_login_params.model_dump_json(exclude_none=True)
    result = await redis.setex(cache_key, 660, login_params_json)
    if bool(result) is False:
        raise Http500


@backoff.on_exception(backoff.expo, ConnectionError, max_time=15)
async def get_cached_yandex_login_data(
    state: UUID4,
    redis: Redis = Depends(get_redis_connection)
) -> YandexIdLoginRequestParams:
    login_params_json = await redis.getdel(f"{YandexAuthRedisPrefix.YALOGIN}:{state}")
    if login_params_json is None:
        raise Http400(f"Failed to find login data for state '{state}'")
    
    try:
        login_params = YandexIdLoginRequestParams.model_validate_json(login_params_json)
    except ValidationError:
        raise Http500

    return login_params


async def get_yandexid_token_request_data(
    code: str,
    cached_login_data: YandexIdLoginRequestParams = Depends(get_cached_yandex_login_data)
) -> YandexIdTokenRequestData:
    login_data_dict = cached_login_data.model_dump(exclude_none=True)
    try:
        token_request_data = YandexIdTokenRequestData(code=code, **login_data_dict)
    except ValidationError:
        raise Http500

    return token_request_data


async def get_yandexid_token_request_components(
    app_settings: Settings = Depends(get_app_settings),
    request_data: YandexIdTokenRequestData = Depends(get_yandexid_token_request_data),
) -> HttpRequestComponents:
    return HttpRequestComponents(
        url=app_settings.oauth_yandex.token_url,
        data=request_data.model_dump(exclude_none=True),
        headers={"Authorization": app_settings.oauth_yandex.auth_header}
    )


async def get_yandexid_user_request_components(
    app_settings: Settings = Depends(get_app_settings),
    request_params: YandexIdUserRequestParams = Depends()
) -> HttpRequestComponents:
    return HttpRequestComponents(
        url=app_settings.oauth_yandex.user_info_url,
        params=request_params.model_dump(exclude_none=True)
    )
