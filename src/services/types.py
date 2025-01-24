from typing import Awaitable, Callable

import httpx
from async_fastapi_jwt_auth import AuthJWT
from redis import Redis

from db.repository import AsyncBaseRepository
from services.oauth.enums import OAuthLoginServiceResult
from services.oauth.schemas import OAuthLoginServiceOutput
from services.schemas import HttpRequestComponents, RequestMeta

OAuthLoginService = Callable[
    [
        RequestMeta,
        AsyncBaseRepository,
        Redis,
        AuthJWT,
        httpx.AsyncClient,
        HttpRequestComponents,
        HttpRequestComponents
    ],
    Awaitable[tuple[OAuthLoginServiceResult, OAuthLoginServiceOutput | None, str | None]]
]
