import datetime
import logging

import backoff
from async_fastapi_jwt_auth import AuthJWT
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

import models
from db.repository import AsyncSqlAlchemyRepository
from schemas.token import TokenInfo
from services.enums import ServiceWorkResults

logger = logging.getLogger(__name__)


async def authorize_by_user_id(
    user_id: str, authorize: AuthJWT, repository: AsyncSqlAlchemyRepository
) -> tuple[ServiceWorkResults, TokenInfo | None, str | None]:
    try:
        user: models.User | None = await repository.get(
            models.User, models.User.id, user_id, [joinedload(models.User.role),]
        )
    except SQLAlchemyError as e:
        logger.exception(f"Database error: {e}")
        return ServiceWorkResults.ERROR, None, None

    if user is None:
        return ServiceWorkResults.FAIL, None, "User not found"
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
    return ServiceWorkResults.SUCCESS, TokenInfo(access=access_token, refresh=refresh_token), "ok"


@backoff.on_exception(backoff.expo, ConnectionError, max_time=15)
async def invalidate_token(
        token: dict,
        redis: Redis,
) -> bool:
    jti = token["jti"]
    exp = token["exp"]
    return await redis.setex(f"blacklist:{jti}", exp - int(datetime.datetime.now().timestamp()), "true")

@backoff.on_exception(backoff.expo, ConnectionError, max_time=15)
async def check_invalid_token(
        token: dict,
        redis: Redis,
) -> bool:
    jti = token["jti"]
    res =  await redis.get(f"blacklist:{jti}")
    return res

