import logging
from functools import partial

import httpx
import sqlalchemy.exc as sa_exc
from async_fastapi_jwt_auth import AuthJWT
from redis.asyncio import Redis

from db.repository import AsyncBaseRepository
from schemas.token import TokenInfo
from services.oauth.enums import OAuthLoginServiceResult, UserAcquireMethod
from services.oauth.schemas import OAuthLoginServiceOutput
from services.schemas import HttpRequestComponents
from ._exceptions import YandexIdRequestError
from ._utils import (
    authorize_with_yandex,
    cache_login_data_for_reconcile,
    create_oauth_account,
    get_or_create_yandex_user,
    update_oauth_account,
)

logger = logging.getLogger(__name__)


async def login(
    repository: AsyncBaseRepository,
    redis: Redis,
    authorize: AuthJWT,
    http_client: httpx.AsyncClient,
    token_request_components: HttpRequestComponents,
    user_request_components: HttpRequestComponents
) -> tuple[OAuthLoginServiceResult, OAuthLoginServiceOutput | None, str | None]:

    try:
        yandex_token_data, yandex_user_data = await authorize_with_yandex(
            http_client, token_request_components, user_request_components
        )
    except YandexIdRequestError as e:
        logger.error(f"Yandex API error: {str(e)}")
        return OAuthLoginServiceResult.FAIL, None, "Failed to communicate with Yandex API"

    try:
        user, user_acquired_by = await get_or_create_yandex_user(repository, yandex_user_data)
    # Для случаев когда нужно привязать к существующему user'у аккаунт яндекса
    except sa_exc.IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        await cache_login_data_for_reconcile(
            redis, yandex_token_data, yandex_user_data.default_email
        )
        service_output = OAuthLoginServiceOutput(user_email=yandex_user_data.default_email)
        return OAuthLoginServiceResult.RECONCILE, service_output, None
    except sa_exc.DatabaseError as e:
        logger.error(f"Database error during processing YandexId data: {str(e)}")
        return OAuthLoginServiceResult.ERROR, None, None

    match user_acquired_by:
        case UserAcquireMethod.GET:
            oauth_account_routine = partial(
                update_oauth_account, repository, yandex_user_data.id, yandex_token_data\
            )
        case UserAcquireMethod.CREATE:
            oauth_account_routine = partial(
                create_oauth_account, repository, user.id, yandex_user_data.id, yandex_token_data
            )
    try:
        await oauth_account_routine()
    except sa_exc.DatabaseError as e:
        logger.error(f"Database error during processing YandexId data: {str(e)}")
        return OAuthLoginServiceResult.ERROR, None, None

    try:
        roles_claim = user.role.title
    except AttributeError:
        roles_claim = None

    claims = {"roles": roles_claim}
    access_token = await authorize.create_access_token(
        subject=str(user.id), user_claims=claims
    )
    refresh_token = await authorize.create_refresh_token(
        subject=str(user.id), user_claims=claims
    )
    tokens = TokenInfo(access=access_token, refresh=refresh_token)
    return OAuthLoginServiceResult.SUCCESS, OAuthLoginServiceOutput(tokens=tokens), "ok"
