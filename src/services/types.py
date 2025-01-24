from typing import Callable

import httpx
from async_fastapi_jwt_auth import AuthJWT
from redis import Redis

from db.repository import AsyncBaseRepository
from services.oauth.enums import OAuthLoginServiceResult
from services.oauth.schemas import OAuthLoginServiceOutput
from services.schemas import HttpRequestComponents

OAuthLoginService = Callable[
    [
        AsyncBaseRepository,
        Redis,
        AuthJWT,
        httpx.AsyncClient,
        HttpRequestComponents,
        HttpRequestComponents
    ],
    tuple[OAuthLoginServiceResult, OAuthLoginServiceOutput | None, str | None]
]
