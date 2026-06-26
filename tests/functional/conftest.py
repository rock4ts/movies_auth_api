from collections.abc import AsyncGenerator, Callable
from functools import lru_cache
from http import HTTPStatus
import json
from typing import Any
import uuid

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio
from pwdlib import PasswordHash
from redis.asyncio import Redis

from tests.functional.settings import DEFAULT_ROLE_TITLE, test_settings

_test_password_hash = PasswordHash.recommended()


@lru_cache
def _jwt_public_key() -> bytes:
    with open("tests/docker/certs/jwt-public.pem", "rb") as key_file:
        return key_file.read()


def _api_path(path: str) -> str:
    prefix = test_settings.api_prefix.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{prefix}{path}"


def _response_payload(response: httpx.Response):
    try:
        return response.json()
    except ValueError:
        return response.text


@pytest_asyncio.fixture(scope="function")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        base_url=test_settings.api_url,
        timeout=test_settings.request_timeout_seconds,
        follow_redirects=False,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="function")
async def make_get_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int]]:
    async def inner(
        path: str, query_data: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int]:
        response = await http_client.get(_api_path(path), params=query_data, headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture(scope="function")
async def make_post_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int, httpx.Response]]:
    async def inner(
        path: str, body: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int, httpx.Response]:
        response = await http_client.post(_api_path(path), json=body, headers=headers)
        return _response_payload(response), response.status_code, response

    return inner


@pytest_asyncio.fixture(scope="function")
async def make_patch_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None, dict | None], tuple[dict | list | str, int]]:
    async def inner(
        path: str, body: dict | None = None, headers: dict | None = None
    ) -> tuple[dict | list | str, int]:
        response = await http_client.patch(_api_path(path), json=body, headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture(scope="function")
async def make_delete_request(
    http_client: httpx.AsyncClient,
) -> Callable[[str, dict | None], tuple[dict | list | str, int]]:
    async def inner(path: str, headers: dict | None = None) -> tuple[dict | list | str, int]:
        response = await http_client.delete(_api_path(path), headers=headers)
        return _response_payload(response), response.status_code

    return inner


@pytest_asyncio.fixture(scope="function")
async def db_cleanup() -> AsyncGenerator[None, None]:
    conn = await asyncpg.connect(
        host=test_settings.postgres_host,
        port=test_settings.postgres_port,
        user=test_settings.postgres_user,
        password=test_settings.postgres_password,
        database=test_settings.postgres_db,
    )
    await conn.execute("DELETE FROM oauth_accounts;")
    await conn.execute("DELETE FROM login_history;")
    await conn.execute(
        "DELETE FROM users WHERE email <> $1;",
        test_settings.superuser_email,
    )
    await conn.execute("DELETE FROM roles WHERE title <> 'user';")
    await conn.close()
    yield


@pytest_asyncio.fixture(scope="function")
async def redis_cleanup() -> AsyncGenerator[None, None]:
    redis = Redis(host=test_settings.redis_host, port=test_settings.redis_port)
    await redis.flushdb()
    await redis.aclose()
    yield


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_state(db_cleanup: None, redis_cleanup: None):
    return None


@pytest_asyncio.fixture(scope="function")
async def user_password() -> str:
    return "UserPassword123!"


@pytest_asyncio.fixture(scope="function")
async def create_user_payload(user_password: str) -> dict[str, str]:
    return {
        "email": f"test_{uuid.uuid4().hex}@example.com",
        "password": user_password,
    }


@pytest_asyncio.fixture(scope="function")
async def create_db_role(db_connection: asyncpg.Connection):
    async def inner(role_title: str, access_labels: list[str]) -> uuid.UUID:
        role_id = uuid.uuid4()
        await db_connection.execute(
            """
            INSERT INTO roles (id, title, access_labels, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW());
            """,
            str(role_id),
            role_title,
            json.dumps(access_labels),
        )
        return role_id

    return inner


@pytest_asyncio.fixture(scope="function")
async def create_db_user(db_connection: asyncpg.Connection) -> Callable[..., uuid.UUID]:
    async def inner(
        email: str,
        password: str | None = None,
        first_name: str = "Local",
        last_name: str = "User",
    ) -> uuid.UUID:
        role_id = await db_connection.fetchval(
            "SELECT id FROM roles WHERE title = $1;",
            DEFAULT_ROLE_TITLE,
        )
        user_id = uuid.uuid4()
        password_hash_value = (
            _test_password_hash.hash(password) if password is not None else "hashed-password"
        )
        await db_connection.execute(
            """
            INSERT INTO users (
                id, email, password_hash, token_version, first_name, last_name,
                role_id, is_superuser, created_at, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, false, NOW(), NOW()
            );
            """,
            user_id,
            email,
            password_hash_value,
            1,
            first_name,
            last_name,
            role_id,
        )
        return user_id

    return inner


@pytest_asyncio.fixture(scope="function")
async def login_user(
    make_post_request: Callable[
        [str, dict | None, dict | None], tuple[dict | list | str, int, httpx.Response]
    ],
) -> Callable[[str, str], tuple[dict, httpx.Response]]:
    async def inner(email: str, password: str) -> tuple[dict, httpx.Response]:
        body, status, response = await make_post_request(
            "/token",
            {"email": email, "password": password},
        )
        assert status == HTTPStatus.OK
        return body, response

    return inner


@pytest_asyncio.fixture(scope="function")
async def superuser_access_token(
    make_post_request: Callable[
        [str, dict | None, dict | None], tuple[dict | list | str, int, httpx.Response]
    ],
) -> str:
    body, status, _ = await make_post_request(
        "/token",
        {
            "email": test_settings.superuser_email,
            "password": test_settings.superuser_password,
        },
    )
    assert status == HTTPStatus.OK
    return body["access"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture(scope="function")
async def db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    conn = await asyncpg.connect(
        host=test_settings.postgres_host,
        port=test_settings.postgres_port,
        user=test_settings.postgres_user,
        password=test_settings.postgres_password,
        database=test_settings.postgres_db,
    )
    yield conn
    await conn.close()


@pytest_asyncio.fixture(scope="function")
async def redis_client() -> AsyncGenerator[Redis, None]:
    client = Redis(host=test_settings.redis_host, port=test_settings.redis_port)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(scope="function")
async def get_user_by_email(
    db_connection: asyncpg.Connection,
) -> Callable[[str], asyncpg.Record | None]:
    async def inner(email: str) -> asyncpg.Record | None:
        return await db_connection.fetchrow("SELECT * FROM users WHERE email = $1;", email)

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_user_by_id(
    db_connection: asyncpg.Connection,
) -> Callable[[str], asyncpg.Record | None]:
    async def inner(user_id: str) -> asyncpg.Record | None:
        return await db_connection.fetchrow("SELECT * FROM users WHERE id = $1;", user_id)

    return inner


@pytest_asyncio.fixture(scope="function")
async def count_users(db_connection: asyncpg.Connection) -> Callable[[], int]:
    async def inner() -> int:
        return await db_connection.fetchval(
            "SELECT COUNT(*) FROM users WHERE email <> $1;",
            test_settings.superuser_email,
        )

    return inner


@pytest_asyncio.fixture(scope="function")
async def count_oauth_accounts(db_connection: asyncpg.Connection) -> Callable[[], int]:
    async def inner() -> int:
        return await db_connection.fetchval("SELECT COUNT(*) FROM oauth_accounts;")

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_oauth_accounts(
    db_connection: asyncpg.Connection,
) -> Callable[[str | None], list[asyncpg.Record]]:
    async def inner(provider_user_id: str | None = None) -> list[asyncpg.Record]:
        if provider_user_id is None:
            return await db_connection.fetch("SELECT * FROM oauth_accounts;")
        return await db_connection.fetch(
            "SELECT * FROM oauth_accounts WHERE provider_user_id = $1;",
            provider_user_id,
        )

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_login_history_for_user(
    db_connection: asyncpg.Connection,
) -> Callable[[uuid.UUID], list[asyncpg.Record]]:
    async def inner(user_id: uuid.UUID) -> list[asyncpg.Record]:
        return await db_connection.fetch(
            "SELECT * FROM login_history WHERE user_id = $1 ORDER BY logged_in_at DESC;",
            user_id,
        )

    return inner


@pytest_asyncio.fixture(scope="function")
async def count_custom_roles(db_connection: asyncpg.Connection) -> Callable[[], int]:
    async def inner() -> int:
        return await db_connection.fetchval("SELECT COUNT(*) FROM roles WHERE title <> 'user';")

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_role_by_id(
    db_connection: asyncpg.Connection,
) -> Callable[[uuid.UUID | str], asyncpg.Record | None]:
    async def inner(role_id: uuid.UUID | str) -> asyncpg.Record | None:
        return await db_connection.fetchrow("SELECT * FROM roles WHERE id = $1;", role_id)

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_role_by_title(
    db_connection: asyncpg.Connection,
) -> Callable[[str], asyncpg.Record | None]:
    async def inner(title: str) -> asyncpg.Record | None:
        return await db_connection.fetchrow("SELECT * FROM roles WHERE title = $1;", title)

    return inner


@pytest_asyncio.fixture(scope="function")
async def get_default_role_id(
    db_connection: asyncpg.Connection,
) -> Callable[[], Any]:
    async def inner() -> uuid.UUID:
        role_id = await db_connection.fetchval(
            "SELECT id FROM roles WHERE title = $1;", DEFAULT_ROLE_TITLE
        )
        assert role_id is not None
        return role_id

    return inner


@pytest_asyncio.fixture(scope="function")
async def is_refresh_token_blacklisted(
    redis_client: Redis,
) -> Callable[[str], bool]:
    async def inner(refresh_token: str) -> bool:
        payload = jwt.decode(
            refresh_token,
            _jwt_public_key(),
            algorithms=["RS256"],
        )
        return await redis_client.get(f"blacklist:{payload['jti']}") is not None

    return inner


@pytest_asyncio.fixture(scope="function")
async def create_oauth_account(db_connection: asyncpg.Connection) -> Callable[..., uuid.UUID]:
    async def inner(
        user_id: uuid.UUID, provider_user_id: str, provider: str = "yandex"
    ) -> uuid.UUID:
        account_id = uuid.uuid4()
        await db_connection.execute(
            """
            INSERT INTO oauth_accounts (
                id, provider, provider_user_id, user_id, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, NOW(), NOW());
            """,
            account_id,
            provider,
            provider_user_id,
            user_id,
        )
        return account_id

    return inner
