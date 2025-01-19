from fastapi.responses import RedirectResponse
import httpx
from pydantic import EmailStr
from redis.asyncio import Redis
from async_fastapi_jwt_auth import AuthJWT
from async_fastapi_jwt_auth.auth_jwt import AuthJWTBearer
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.exceptions import Http400, Http500
from db.redis import get_redis_connection
from db.repository import AsyncBaseRepository
from models.history import LoginHistory
from schemas.enums import ServiceWorkResults
from schemas.token import TokenInfo
from schemas.user import UserBaseOut, UserIn, UserLogin
from services.auth.yandex import service as ya_service
from services.auth.yandex.enums import YandexLoginServiceResult
from services.auth.yandex.schemas import HttpRequestComponents
from services.token import authorize_by_user_id, invalidate_token, check_invalid_token
from services.users import create_user as services_create_user, get_user_by_email
from services.users import validate_auth_user_login

from .dependencies import (
    cache_oauth_login_params,
    get_http_client,
    get_oauth_login_redirect,
    get_session,
    check_superuser,
    get_sqlalchemy_repository,
    check_invalid_token as check_invalid_token_depcy,
    get_yandexid_token_request_components,
    get_yandexid_user_request_components,
)

router = APIRouter()
auth_bearer = AuthJWTBearer()


@router.post("/register", response_model=UserBaseOut)
async def create_user(
    user_create: UserIn,
    session: AsyncSession = Depends(get_session),
) -> UserBaseOut:
    existing_user = await get_user_by_email(
        user_create.email,
        session,
    )
    if existing_user:
        raise HTTPException(
            status_code=400, detail="User with this username or email already exists"
        )
    user = await services_create_user(
        user_create=user_create,
        session=session,
    )
    return user


@router.post("/login", response_model=TokenInfo)
async def login(
    user: UserLogin,
    request: Request,
    session: AsyncSession = Depends(get_session),
    authorize: AuthJWT = Depends(auth_bearer),
) -> TokenInfo:
    validated_user = await validate_auth_user_login(user, session)
    try:
        roles_claim = validated_user.role.title
    except AttributeError:
        roles_claim = None

    claims = {
        "email": validated_user.email,
        "first_name": validated_user.first_name,
        "last_name": validated_user.last_name,
        "roles": roles_claim
    }
    # Создание токенов
    access_token = await authorize.create_access_token(
        subject=str(validated_user.id), user_claims=claims
    )
    refresh_token = await authorize.create_refresh_token(
        subject=str(validated_user.id), user_claims=claims
    )

    # Сохранение истории входа
    ip_address = request.client.host
    user_agent = request.headers.get("user-agent", "unknown")
    login_history = LoginHistory(
        user_id=validated_user.id, ip_address=ip_address, user_agent=user_agent
    )
    session.add(login_history)
    await session.commit()

    return TokenInfo(access=access_token, refresh=refresh_token)


@router.post("/refresh")
async def refresh(
    authorize: AuthJWT = Depends(auth_bearer),
) -> TokenInfo:
    try:
        await authorize.jwt_refresh_token_required()
        current_user = await authorize.get_jwt_subject()
        payload = await authorize.get_raw_jwt()
        new_access_token = await authorize.create_access_token(
            subject=current_user, user_claims=payload
        )
        new_refresh_token = await authorize.create_refresh_token(
            subject=current_user, user_claims=payload
        )
        return TokenInfo(access=new_access_token, refresh=new_refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh token invalid")


@router.post("/logout")
async def logout(
    authorize: AuthJWT = Depends(auth_bearer), redis: Redis = Depends(get_redis_connection)
) -> Response:
    try:
        await authorize.jwt_required()
        token = await authorize.get_raw_jwt()
        if await check_invalid_token(token, redis):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid")
        if await invalidate_token(token, redis):
            return Response(status_code=200)
    except ConnectionError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Request cannot be completed"
        )
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalid")


@router.post(
    "/supervised_login/{user_id}",
    dependencies=[Depends(check_invalid_token_depcy), Depends(check_superuser),]
)
async def supervised_login(
    user_id: str,
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
    authorize: AuthJWT = Depends(auth_bearer)
) -> TokenInfo:
    result, token_pair, res_msg = await authorize_by_user_id(user_id, authorize, repository)

    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return token_pair


@router.get("/{provider}/login", dependencies=[Depends(cache_oauth_login_params),])
async def oauth_login(
    redirect = Depends(get_oauth_login_redirect),  # noqa: ANN001 as per https://github.com/fastapi/fastapi/discussions/9897
) -> RedirectResponse:
    return redirect


@router.post("/yandex/token")
async def confirm_login_yandex(
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
    redis: Redis = Depends(get_redis_connection),
    authorize: AuthJWT = Depends(auth_bearer),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    token_request_components: HttpRequestComponents = Depends(get_yandexid_token_request_components),
    user_request_components: HttpRequestComponents = Depends(get_yandexid_user_request_components)
) -> TokenInfo:
    result, service_output, res_msg = await ya_service.login(
        repository,
        redis,
        authorize,
        http_client,
        token_request_components,
        user_request_components
    )

    if result is YandexLoginServiceResult.RECONCILE:
        return RedirectResponse(
            url=f"/auth/yandex/reconcile?user_email={service_output.user_email}",
            status_code=302,
        )
    if result is YandexLoginServiceResult.ERROR:
        raise Http500
    if result is YandexLoginServiceResult.FAIL:
        raise Http400(res_msg)

    return service_output.tokens


# С помощью отправки
# Получаем юзера по email и предлагаем подтвердить кодом на почту
# или пропустить подтверждение и создать аккаунт без привязки к почте (# TODO требует доработки)
# Далее создаём oauth аккаунт используя закэшированные данные
@router.get("/yandex/reconcile")
async def reconcile_yandex_user(user_email: EmailStr) -> None:
    pass
