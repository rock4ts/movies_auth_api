from http import HTTPStatus
import json

import pytest

from src.settings import webapp_settings


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_yandex_redirects(http_client) -> None:  # noqa: ANN001
    response = await http_client.get(f"{webapp_settings.service_url}/yandex")

    assert response.status == HTTPStatus.OK
    assert response.url.host == "oauth.yandex.ru"


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_yandex_caches_state(get_cache_by_prefix, make_get_request) -> None:  # noqa: ANN001
    cache_before = await get_cache_by_prefix("yandex")
    assert cache_before == []

    await make_get_request("/yandex")

    cache_after = await get_cache_by_prefix("yandex")
    assert cache_after != []

    state = json.loads(cache_after[0])["state"]
    assert state is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_yandex_webhook_creates_and_logs_in_user(
    get_user_by_email, get_cache_by_prefix, make_get_request, make_post_request
) -> None:
    user_before_login = await get_user_by_email(webapp_settings.oauth_yandex_email)
    assert user_before_login is None

    await make_get_request("/yandex")

    cached_login_data = await get_cache_by_prefix("yandex")
    state = json.loads(cached_login_data[0])["state"]
    login_tokens, status = await make_post_request(
        f"/yandex/login?grant_type=authorization_code&state={state}"
        f"&code={webapp_settings.oauth_yandex_mock_code}"
    )
    assert status == HTTPStatus.OK
    assert login_tokens["access"] is not None
    assert login_tokens["refresh"] is not None
    user_after_login = await get_user_by_email(webapp_settings.oauth_yandex_email)
    assert user_after_login is not None
