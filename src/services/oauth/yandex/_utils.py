import backoff
import httpx
import sqlalchemy.exc as sa_exc
from pydantic import UUID4, EmailStr
from redis import exceptions as redis_exc
from redis.asyncio import Redis

import models
from db.repository import AsyncBaseRepository
from schemas.enums import OAuthProviders
from services.oauth.enums import UserAcquireMethod
from services.schemas import HttpRequestComponents

from ._exceptions import YandexIdRequestError
from .enums import YandexAuthRedisPrefix
from .schemas import (
    ReconcileYandexIdUserData,
    YandexIdTokenData,
    YandexIdUserData,
)


@backoff.on_exception(backoff.expo, httpx.RequestError, max_time=5)
async def _request_token(
    http_client: httpx.AsyncClient, 
    token_request_components: HttpRequestComponents
) -> httpx.Response:
    return await http_client.post(
        url=token_request_components.url.unicode_string(),
        data=token_request_components.data,
        headers=token_request_components.headers
    )


@backoff.on_exception(backoff.expo, httpx.RequestError, max_time=5)
async def _request_user_data(
    http_client: httpx.AsyncClient,
    user_request_components: HttpRequestComponents,
    yandex_token: str
) -> httpx.Response:
    return await http_client.get(
        url=user_request_components.url.unicode_string(),
        params=user_request_components.params,
        headers={"Authorization": f"OAuth {yandex_token}"}
    )


async def authorize_with_yandex(
    http_client: httpx.AsyncClient,
    token_request_components: HttpRequestComponents,
    user_request_components: HttpRequestComponents
) -> tuple[YandexIdTokenData, YandexIdUserData]:

    try:
        response = await _request_token(http_client, token_request_components)
    except httpx.RequestError as e:
        raise YandexIdRequestError(str(e))

    response_data = response.json()
    if response.is_error:
        raise YandexIdRequestError(response_data["error_description"])

    yandex_token_data = YandexIdTokenData(**response_data)

    try:
        response = await _request_user_data(
            http_client, user_request_components, yandex_token_data.access_token
        )
    except httpx.RequestError as e:
        raise YandexIdTokenData(str(e))

    response_data = response.json()
    if response.is_error:
        raise YandexIdRequestError(response_data["error_description"])

    yandex_user_data = YandexIdUserData(**response_data)
    return yandex_token_data, yandex_user_data


@backoff.on_exception(backoff.expo, redis_exc.ConnectionError, max_time=5)
async def cache_login_data_for_reconcile(
    redis: Redis, yandex_token_data: YandexIdTokenData, user_email: EmailStr
) -> None:
    reconcile_data = ReconcileYandexIdUserData(default_email=user_email, **yandex_token_data.model_dump())
    await redis.setex(
        f"{YandexAuthRedisPrefix.YATOKEN}:{user_email}",
        600,
        reconcile_data.model_dump_json(exclude_none=True)
    )


@backoff.on_exception(backoff.expo, sa_exc.DatabaseError, max_time=5)
async def get_or_create_yandex_user(
    repository: AsyncBaseRepository,
    yandex_user_data: YandexIdUserData
) -> tuple[models.User | None, UserAcquireMethod]:
    db_user = await repository.get(
        models.User,
        joins=[models.User.oauth_accounts],
        join_filters=[models.OAuthAccount.external_user_id == yandex_user_data.id]
    )
    if db_user is not None:
        return db_user, UserAcquireMethod.GET

    new_user = models.User(
        email=yandex_user_data.default_email,
        first_name=yandex_user_data.first_name,
        last_name=yandex_user_data.last_name
    )
    new_user.set_password()
    db_user = await repository.add(new_user)
    return db_user, UserAcquireMethod.CREATE


@backoff.on_exception(backoff.expo, sa_exc.DatabaseError, max_time=5)
async def update_oauth_account(
    repository: AsyncBaseRepository,
    yandex_user_id: str,
    yandex_token_data: YandexIdTokenData
) -> None:
    await repository.update(
        models.OAuthAccount,
        [models.OAuthAccount.external_user_id == yandex_user_id,],
        {models.OAuthAccount.access_data.name: yandex_token_data.model_dump(),}
    )


@backoff.on_exception(backoff.expo, sa_exc.DatabaseError, max_time=5)
async def create_oauth_account(
    repository: AsyncBaseRepository,
    user_id: UUID4,
    yandex_user_id: str,
    yandex_token_data: YandexIdTokenData
) -> tuple[models.OAuthAccount, UserAcquireMethod]:

    new_oauth_account = models.OAuthAccount(
        user_id=user_id,
        provider=OAuthProviders.YANDEX,
        external_user_id=yandex_user_id,
        access_data=yandex_token_data.model_dump()
    )
    db_oauth_account = await repository.add(new_oauth_account)
    return db_oauth_account
