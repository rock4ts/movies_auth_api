from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, Response
from fastapi.params import Depends
from fastapi.responses import RedirectResponse
from app.core.config import jwt_settings, settings, yandexid_settings
from app.schemas.auth import AccessTokenResponse
from app.schemas.misc import RequestMeta
from app.services.service_yandexid import (
    YandexIdAccountConflictError,
    YandexIdProviderError,
    YandexIdService,
    YandexIdStateError,
    YandexIdTokenError,
    YandexIdUserInfoError,
)

from .dependencies import (
    get_device_info,
    get_request_meta,
    get_yandexid_service,
    rate_limit_route_by_ip,
)
from app.schemas.misc import DeviceInfo
from .exceptions import (
    OAuthCallbackHttpException,
    OAuthProviderHttpException,
    OAuthStateHttpException,
)

router = APIRouter()


def generate_login_state() -> UUID:
    return uuid4()


def validate_login_state(request: Request, state: UUID) -> None:
    cookie_state_raw = request.cookies.get("state")

    if not cookie_state_raw:
        raise OAuthStateHttpException("Cookie state is invalid or expired")
    try:
        cookie_state = UUID(cookie_state_raw)
    except ValueError:
        raise OAuthStateHttpException("Cookie state is invalid or expired")
    if state != cookie_state:
        raise OAuthStateHttpException("Login state is invalid or expired")


@router.get("/login")
async def oauth_login(
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    state: Annotated[UUID, Depends(generate_login_state)],
    yandexid_service: Annotated[YandexIdService, Depends(get_yandexid_service)],
) -> RedirectResponse:
    try:
        redirect_url = await yandexid_service.build_login_redirect(state)
    except YandexIdProviderError:
        raise OAuthProviderHttpException("Failed to initialize Yandex OAuth")

    response = RedirectResponse(
        url=redirect_url,
        status_code=302,
        headers={"Authorization": yandexid_settings.auth_header},
    )
    response.set_cookie(
        key="state",
        value=str(state),
        samesite="lax",
        httponly=True,
        secure=settings.prod,
        max_age=yandexid_settings.confirmation_code_ttl,
    )
    return response


@router.get("/token")
async def confirm_login_yandex(
    response: Response,
    code: str,
    state: UUID,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    _validate_login_state: Annotated[None, Depends(validate_login_state)],
    request_meta: Annotated[RequestMeta, Depends(get_request_meta)],
    device_info: Annotated[DeviceInfo, Depends(get_device_info)],
    yandexid_service: Annotated[YandexIdService, Depends(get_yandexid_service)],
) -> AccessTokenResponse:
    try:
        tokens = await yandexid_service.authorize(
            code=code, state=state, request_meta=request_meta, device_info=device_info
        )
    except YandexIdStateError:
        raise OAuthStateHttpException()
    except YandexIdTokenError:
        raise OAuthProviderHttpException("Error during token exchange with provider")
    except YandexIdUserInfoError:
        raise OAuthProviderHttpException("Error during user profile fetch from provider")
    except YandexIdProviderError:
        raise OAuthProviderHttpException()
    except YandexIdAccountConflictError:
        raise OAuthCallbackHttpException("Yandex account link conflict")

    response.delete_cookie(key="state")
    response.set_cookie(
        key="device_id",
        value=str(device_info.device_id),
        samesite="lax",
        httponly=True,
        secure=settings.prod,
    )
    response.set_cookie(
        key="refresh",
        value=tokens.refresh,
        samesite="lax",
        httponly=True,
        secure=settings.prod,
        max_age=jwt_settings.refresh_token_expire_days * 60 * 60 * 24,
    )
    return AccessTokenResponse(access=tokens.access)
