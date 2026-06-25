from http import HTTPStatus
import json
from typing import Any
import uuid

import pytest

from tests.functional.conftest import auth_headers
from tests.functional.settings import DEFAULT_ROLE_ACCESS_LABELS, DEFAULT_ROLE_TITLE


@pytest.mark.asyncio
async def test_non_superuser_cannot_list_roles(
    create_user_payload,
    create_db_user,
    login_user,
    make_get_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    body, status = await make_get_request("/roles", headers=auth_headers(login_body["access"]))

    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "User is not a superuser"


@pytest.mark.asyncio
async def test_non_superuser_cannot_create_role(
    create_user_payload,
    create_db_user,
    login_user,
    make_post_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    body, status, _ = await make_post_request(
        "/roles",
        body={"title": "test-role", "access_labels": DEFAULT_ROLE_ACCESS_LABELS},
        headers=auth_headers(login_body["access"]),
    )
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "User is not a superuser"


@pytest.mark.asyncio
async def test_non_superuser_cannot_modify_role(
    create_user_payload,
    create_db_user,
    login_user,
    make_patch_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    body, status = await make_patch_request(
        "/roles/1",
        body={"title": "test-role", "access_labels": DEFAULT_ROLE_ACCESS_LABELS},
        headers=auth_headers(login_body["access"]),
    )
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "User is not a superuser"


@pytest.mark.asyncio
async def test_non_superuser_cannot_delete_role(
    create_user_payload,
    create_db_user,
    login_user,
    make_delete_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    body, status = await make_delete_request(
        "/roles/1",
        headers=auth_headers(login_body["access"]),
    )
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "User is not a superuser"


@pytest.mark.asyncio
async def test_non_superuser_cannot_assign_role(
    create_user_payload,
    create_db_user,
    login_user,
    make_post_request,
):
    await create_db_user(create_user_payload["email"], password=create_user_payload["password"])
    login_body, _ = await login_user(create_user_payload["email"], create_user_payload["password"])
    body, status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": "1", "user_id": "1"},
        headers=auth_headers(login_body["access"]),
    )
    assert status == HTTPStatus.UNAUTHORIZED
    assert body["detail"] == "User is not a superuser"


@pytest.mark.asyncio
async def test_create_and_list_roles(
    make_post_request,
    make_get_request,
    superuser_access_token,
    count_custom_roles,
    get_role_by_title,
):
    superuser_access = superuser_access_token
    role_title = f"qa-role-{uuid.uuid4().hex[:8]}"

    assert await count_custom_roles() == 0
    created_body, created_status, _ = await make_post_request(
        "/roles",
        body={"title": role_title, "access_labels": ["free", "vip"]},
        headers=auth_headers(superuser_access),
    )
    assert created_status == HTTPStatus.OK
    assert created_body["title"] == role_title
    assert created_body["access_labels"] == ["free", "vip"]
    assert created_body["id"] is not None

    assert await count_custom_roles() == 1
    role = await get_role_by_title(role_title)
    assert role is not None
    assert json.loads(role["access_labels"]) == ["free", "vip"]
    assert role["id"] == uuid.UUID(str(created_body["id"]))

    listed_body, listed_status = await make_get_request(
        "/roles", headers=auth_headers(superuser_access)
    )
    assert listed_status == HTTPStatus.OK
    assert len(listed_body) == 2
    for rt in [role_title, DEFAULT_ROLE_TITLE]:
        assert rt in [role["title"] for role in listed_body]


@pytest.mark.asyncio
async def test_duplicate_role_returns_bad_request(
    make_post_request,
    superuser_access_token,
    count_custom_roles,
):
    superuser_access = superuser_access_token
    role_title = f"dup-role-{uuid.uuid4().hex[:8]}"
    payload = {"title": role_title, "access_labels": DEFAULT_ROLE_ACCESS_LABELS}

    _, first_status, _ = await make_post_request(
        "/roles",
        body=payload,
        headers=auth_headers(superuser_access),
    )
    assert first_status == HTTPStatus.OK
    roles_after_first = await count_custom_roles()

    duplicate_body, duplicate_status, _ = await make_post_request(
        "/roles",
        body=payload,
        headers=auth_headers(superuser_access),
    )

    assert duplicate_status == HTTPStatus.BAD_REQUEST
    assert duplicate_body["detail"] == "Role already exists"
    assert await count_custom_roles() == roles_after_first


@pytest.mark.asyncio
async def test_default_role_is_protected_from_delete(
    make_get_request,
    make_delete_request,
    superuser_access_token,
    get_role_by_id,
):
    superuser_access = superuser_access_token
    roles, roles_status = await make_get_request("/roles", headers=auth_headers(superuser_access))
    assert roles_status == HTTPStatus.OK
    default_role = next(role for role in roles if role["title"] == DEFAULT_ROLE_TITLE)

    body, status = await make_delete_request(
        f"/roles/{default_role['id']}",
        headers=auth_headers(superuser_access),
    )
    assert status == HTTPStatus.BAD_REQUEST
    assert body["detail"] == "Default role is protected"

    db_role = await get_role_by_id(default_role["id"])
    assert db_role is not None


@pytest.mark.asyncio
async def test_assign_role_updates_user_role_id(
    create_user_payload,
    create_db_user,
    create_db_role,
    get_default_role_id,
    make_post_request,
    superuser_access_token,
    get_user_by_email,
):
    superuser_access = superuser_access_token
    user_id = await create_db_user(
        create_user_payload["email"], password=create_user_payload["password"]
    )
    db_user = await get_user_by_email(create_user_payload["email"])
    default_role_id = await get_default_role_id()
    assert db_user["role_id"] == default_role_id
    role_id = await create_db_role("assigned-role", ["premium"])

    _, assign_status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": str(role_id), "user_id": str(user_id)},
        headers=auth_headers(superuser_access),
    )
    assert assign_status == HTTPStatus.OK

    db_user = await get_user_by_email(create_user_payload["email"])
    assert default_role_id != role_id
    assert db_user["role_id"] == role_id


@pytest.mark.asyncio
async def test_revoke_role_resets_user_to_default_role(
    create_user_payload,
    create_db_user,
    create_db_role,
    make_post_request,
    superuser_access_token,
    get_user_by_email,
    get_default_role_id,
):
    superuser_access = superuser_access_token
    user_id = await create_db_user(
        create_user_payload["email"], password=create_user_payload["password"]
    )
    role_id = await create_db_role("assigned-role", ["premium"])

    _, assign_status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": str(role_id), "user_id": str(user_id)},
        headers=auth_headers(superuser_access),
    )
    assert assign_status == HTTPStatus.OK

    db_user_before_revoke = await get_user_by_email(create_user_payload["email"])
    assert db_user_before_revoke["role_id"] == role_id

    _, revoke_status, _ = await make_post_request(
        "/roles/revoke",
        body={"user_id": str(user_id)},
        headers=auth_headers(superuser_access),
    )
    assert revoke_status == HTTPStatus.OK

    default_role_id = await get_default_role_id()
    db_user_after_revoke = await get_user_by_email(create_user_payload["email"])
    assert default_role_id != role_id
    assert db_user_after_revoke["role_id"] == default_role_id


@pytest.mark.asyncio
async def test_modify_role_and_delete_role(
    make_patch_request,
    make_delete_request,
    superuser_access_token,
    get_role_by_id,
    count_custom_roles,
    create_db_role,
):
    superuser_access = superuser_access_token
    role_title = f"modify-role-{uuid.uuid4().hex[:8]}"
    updated_title = f"{role_title}-updated"

    role_id: Any = await create_db_role("modify-role", ["premium"])
    assert await count_custom_roles() == 1

    _, patch_status = await make_patch_request(
        f"/roles/{role_id}",
        body={"title": updated_title, "access_labels": ["premium"]},
        headers=auth_headers(superuser_access),
    )
    assert patch_status == HTTPStatus.OK

    updated_role = await get_role_by_id(role_id)
    assert updated_role is not None
    assert updated_role["title"] == updated_title
    assert DEFAULT_ROLE_ACCESS_LABELS != ["premium"]
    assert json.loads(updated_role["access_labels"]) == ["premium"]

    _, delete_status = await make_delete_request(
        f"/roles/{role_id}",
        headers=auth_headers(superuser_access),
    )
    assert delete_status == HTTPStatus.OK

    assert await get_role_by_id(role_id) is None
    assert await count_custom_roles() == 0


@pytest.mark.asyncio
async def test_assign_role_returns_not_found_for_unknown_entities(
    create_user_payload,
    get_default_role_id,
    get_role_by_id,
    create_db_user,
    make_post_request,
    superuser_access_token,
    count_custom_roles,
    get_user_by_id,
):
    superuser_access = superuser_access_token
    user_id = await create_db_user(
        create_user_payload["email"], password=create_user_payload["password"]
    )
    bad_role_id = str(uuid.uuid4())
    role = await get_role_by_id(bad_role_id)
    assert role is None
    body, status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": bad_role_id, "user_id": str(user_id)},
        headers=auth_headers(superuser_access),
    )
    assert status == HTTPStatus.NOT_FOUND
    assert body["detail"] == "Role not found"
    assert await count_custom_roles() == 0

    default_role_id = await get_default_role_id()
    bad_user_id = str(uuid.uuid4())
    user = await get_user_by_id(bad_user_id)
    assert user is None
    body, status, _ = await make_post_request(
        "/roles/assign",
        body={"role_id": str(default_role_id), "user_id": bad_user_id},
        headers=auth_headers(superuser_access),
    )
    assert status == HTTPStatus.NOT_FOUND
    assert body["detail"] == "User not found"
