import httpx
from async_fastapi_jwt_auth import AuthJWT
from async_fastapi_jwt_auth.auth_jwt import AuthJWTBearer
from fastapi import APIRouter
from fastapi.params import Depends
from fastapi.responses import RedirectResponse
from pydantic import EmailStr
from redis.asyncio import Redis

from api.exceptions import Http400, Http500
from db.redis import get_redis_connection
from db.repository import AsyncBaseRepository
from schemas.token import TokenInfo
from services.oauth.enums import OAuthLoginServiceResult
from services.oauth.yandex import service as ya_service
from services.oauth.yandex.schemas import HttpRequestComponents

from .dependencies import (
    cache_oauth_login_params,
    get_http_client,
    get_oauth_login_redirect,
    get_sqlalchemy_repository,
    get_yandexid_token_request_components,
    get_yandexid_user_request_components,
)

router = APIRouter()
auth_bearer = AuthJWTBearer()


@router.get("/{provider}/login", dependencies=[Depends(cache_oauth_login_params),])
async def oauth_login(
    redirect = Depends(get_oauth_login_redirect),  # noqa: ANN001 as per https://github.com/fastapi/fastapi/discussions/9897
) -> RedirectResponse:
    return redirect


@router.post("/{provider}/token")
async def confirm_login_yandex(
    provider: str,
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
    redis: Redis = Depends(get_redis_connection),
    authorize: AuthJWT = Depends(auth_bearer),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    token_request_components: HttpRequestComponents = Depends(get_yandexid_token_request_components),
    user_request_components: HttpRequestComponents = Depends(get_yandexid_user_request_components),
) -> TokenInfo:
    result, service_output, res_msg = await ya_service.login(
        repository,
        redis,
        authorize,
        http_client,
        token_request_components,
        user_request_components
    )

    if result is OAuthLoginServiceResult.RECONCILE:
        return RedirectResponse(
            url=f"/auth/{provider}/reconcile?user_email={service_output.user_email}",
            status_code=302,
        )
    if result is OAuthLoginServiceResult.ERROR:
        raise Http500
    if result is OAuthLoginServiceResult.FAIL:
        raise Http400(res_msg)

    return service_output.tokens


# С помощью отправки
# Получаем юзера по email и предлагаем подтвердить кодом на почту
# или пропустить подтверждение и создать аккаунт без привязки к почте (# TODO требует доработки)
# Далее создаём oauth аккаунт используя закэшированные данные
@router.get("/yandex/reconcile")
async def reconcile_yandex_user(user_email: EmailStr) -> None:
    pass
