import logging
from collections.abc import AsyncGenerator
from typing import Annotated, cast
from uuid import UUID, uuid4

import jwt
import user_agents
from fastapi import Request
from fastapi.params import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import jwt_settings
from app.core.request_context import get_client_ip
from app.db.clients import async_session, redis
from app.db.models import User
from app.schemas.auth import AccessTokenPayload
from app.schemas.misc import DeviceInfo, RequestMeta
from app.services.service_auth import AuthService
from app.services.service_role import RoleService
from app.services.service_user import UserService
from app.services.service_yandexid import YandexIdService

from .exceptions import CredentialsHttpException, RefreshHttpException
from .rate_limiter import RedisFixedWindowRateLimiter, enforce_rate_limit, ip_per_route_rule

logger = logging.getLogger(__name__)
oauth2_scheme = HTTPBearer()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


def get_request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


def get_or_create_device_id(request: Request) -> UUID:
    raw_device_id = request.cookies.get("device_id")
    if not raw_device_id:
        return uuid4()
    try:
        return UUID(raw_device_id)
    except ValueError:
        return uuid4()


def get_device_info(
    device_id: Annotated[UUID, Depends(get_or_create_device_id)],
    request_meta: Annotated[RequestMeta, Depends(get_request_meta)],
) -> DeviceInfo | None:

    if request_meta.user_agent:
        device = user_agents.parse(request_meta.user_agent).device
        device_name = f"{device.family} {device.brand} {device.model}".strip()
    else:
        device_name = None

    return DeviceInfo(
        device_id=device_id,
        device_name=device_name,
    )


def get_refresh_token(request: Request) -> str:
    refresh_token = request.cookies.get("refresh")
    if not refresh_token:
        raise RefreshHttpException("Refresh token is required")
    return refresh_token


def get_rate_limiter() -> RedisFixedWindowRateLimiter:
    return RedisFixedWindowRateLimiter(redis=redis)


async def rate_limit_route_by_ip(
    request: Request,
    limiter: Annotated[RedisFixedWindowRateLimiter, Depends(get_rate_limiter)],
) -> None:
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    route_key = f"{request.method}:{route_path}"
    await enforce_rate_limit(
        request=request,
        rule=ip_per_route_rule(),
        identity=f"{get_client_ip(request)}:{route_key}",
        limiter=limiter,
    )


def get_auth_service(session: Annotated[AsyncSession, Depends(get_session)]) -> AuthService:
    return AuthService(session)


def get_user_service(session: Annotated[AsyncSession, Depends(get_session)]) -> UserService:
    return UserService(session)


def get_role_service(session: Annotated[AsyncSession, Depends(get_session)]) -> RoleService:
    return RoleService(session)


def get_yandexid_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> YandexIdService:
    return YandexIdService(session)


def get_access_token_payload(
    token: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_scheme)],
) -> AccessTokenPayload:
    try:
        payload = cast(
            dict[str, object],
            jwt.decode(
                token.credentials, jwt_settings.public_key, algorithms=[jwt_settings.algorithm]
            ),
        )
    except jwt.ExpiredSignatureError:
        raise CredentialsHttpException("Token has expired") from None
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid token: {str(e)}")
        raise CredentialsHttpException("Invalid token") from None

    try:
        validated_payload = AccessTokenPayload.model_validate(payload)
    except ValidationError:
        raise CredentialsHttpException("Invalid token payload") from None
    if validated_payload.type != "access":
        raise CredentialsHttpException("Token is not an access token")
    return validated_payload


async def get_token_user(
    payload: Annotated[AccessTokenPayload, Depends(get_access_token_payload)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    user = await session.get(User, payload.sub)
    if not user:
        raise CredentialsHttpException("User not found")
    if payload.tv != user.token_version:
        raise CredentialsHttpException("Token version mismatch")
    return user


async def ensure_superuser(
    payload: Annotated[AccessTokenPayload, Depends(get_access_token_payload)],
) -> None:
    if not payload.is_superuser:
        raise CredentialsHttpException("User is not a superuser")
