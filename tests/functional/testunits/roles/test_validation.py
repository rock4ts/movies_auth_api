from http import HTTPStatus

import pytest

from tests.functional.conftest import auth_headers
from tests.functional.settings import DEFAULT_ROLE_ACCESS_LABELS


@pytest.mark.asyncio
async def test_delete_role_requires_valid_uuid(make_delete_request, superuser_access_token):
    superuser_access = superuser_access_token
    _, status = await make_delete_request(
        "/roles/not-a-uuid",
        headers=auth_headers(superuser_access),
    )
    assert status == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_assign_role_payload_validation(make_post_request, superuser_access_token):
    superuser_access = superuser_access_token
    _, status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": "not-a-uuid"},
        headers=auth_headers(superuser_access),
    )
    assert status == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_modify_role_payload_validation(
    make_post_request,
    make_patch_request,
    superuser_access_token,
):
    superuser_access = superuser_access_token
    created_role, create_status, _ = await make_post_request(
        "/roles",
        body={"title": "role-for-validation", "access_labels": DEFAULT_ROLE_ACCESS_LABELS},
        headers=auth_headers(superuser_access),
    )
    assert create_status == HTTPStatus.OK

    _, patch_status = await make_patch_request(
        f"/roles/{created_role['id']}",
        body={"title": "role-for-validation-updated"},
        headers=auth_headers(superuser_access),
    )
    assert patch_status == HTTPStatus.UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_roles_require_authorization(make_get_request):
    body, status = await make_get_request("/roles")

    assert status == HTTPStatus.FORBIDDEN
    assert body["detail"] == "Not authenticated"
