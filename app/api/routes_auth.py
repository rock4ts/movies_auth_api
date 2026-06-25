from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Response, status
from fastapi.params import Depends

from app.db.models import User
from app.schemas.auth import AccessTokenResponse, UserLoginData
from app.schemas.misc import RequestMeta
from app.services.service_auth import AuthService, RefreshTokenError, WrongCredentialsError

from app.core.config import jwt_settings, settings

from .dependencies import (
    get_token_user,
    get_auth_service,
    get_device_info,
    get_refresh_token,
    get_request_meta,
    rate_limit_route_by_ip,
)
from app.schemas.misc import DeviceInfo
from .exceptions import CredentialsHttpException, RefreshHttpException

router = APIRouter()


@router.post("/token")
async def issue_tokens(
    response: Response,
    login_data: UserLoginData,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    request_meta: Annotated[RequestMeta, Depends(get_request_meta)],
    device_info: Annotated[DeviceInfo, Depends(get_device_info)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessTokenResponse:
    try:
        tokens = await auth_service.login_user(login_data, request_meta, device_info)
    except WrongCredentialsError:
        raise CredentialsHttpException()
    response.set_cookie(
        key="refresh",
        value=tokens.refresh,
        samesite="lax",
        httponly=True,
        secure=settings.prod,
        max_age=jwt_settings.refresh_token_expire_days * 60 * 60 * 24,
    )
    response.set_cookie(
        key="device_id",
        value=str(device_info.device_id),
        samesite="lax",
        httponly=True,
        secure=settings.prod,
    )

    return AccessTokenResponse(access=tokens.access)


@router.post("/refresh")
async def refresh_tokens(
    response: Response,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessTokenResponse:
    try:
        tokens = await auth_service.refresh_tokens(refresh_token)
    except RefreshTokenError:
        raise RefreshHttpException("Invalid refresh token")

    response.set_cookie(
        key="refresh",
        value=tokens.refresh,
        samesite="lax",
        httponly=True,
        secure=settings.prod,
        max_age=jwt_settings.refresh_token_expire_days * 60 * 60 * 24,
    )
    return AccessTokenResponse(access=tokens.access)


@router.post("/logout")
async def logout(
    response: Response,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> Response:
    try:
        await auth_service.logout(refresh_token)
    except RefreshTokenError:
        raise RefreshHttpException("Invalid refresh token")
    response.delete_cookie(key="refresh")
    response.status_code = status.HTTP_200_OK
    return response


@router.post("/logout-others")
async def logout_others(
    response: Response,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    user: Annotated[User, Depends(get_token_user)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> AccessTokenResponse:
    tokens = await auth_service.logout_others(user)
    response.set_cookie(
        key="refresh",
        value=tokens.refresh,
        samesite="lax",
        httponly=True,
        secure=settings.prod,
        max_age=jwt_settings.refresh_token_expire_days * 60 * 60 * 24,
    )
    return AccessTokenResponse(access=tokens.access)
