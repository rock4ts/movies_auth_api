from typing import Annotated
from fastapi import APIRouter, Response, status
from fastapi.params import Depends
from pydantic import UUID4


from app.api.exceptions import (
    ProtectedRoleHttpError,
    RoleAlreadyExistsHttpError,
    RoleNotFoundHttpError,
    UserNotFoundHttpError,
)
from app.schemas.role import (
    AssignRoleIn,
    ReadRoleOut,
    RoleCreateIn,
    RoleCreateOut,
    RevokeRoleIn,
    UpdateRoleIn,
)
from app.services.service_base import UserNotFoundError
from app.services.service_role import (
    ProtectedRoleError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    RoleService,
)
from .dependencies import get_role_service, ensure_superuser


router = APIRouter(
    dependencies=[
        Depends(ensure_superuser),
    ]
)


@router.post("")
async def create_role(
    role_data_in: RoleCreateIn,
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> RoleCreateOut:
    try:
        return await role_service.create_role(role_data_in)
    except RoleAlreadyExistsError:
        raise RoleAlreadyExistsHttpError()


@router.get("")
async def list_roles(
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> list[ReadRoleOut]:
    return await role_service.get_all_roles()


@router.delete("/{role_id}")
async def delete_role(
    role_id: UUID4, role_service: Annotated[RoleService, Depends(get_role_service)]
) -> Response:
    try:
        await role_service.remove_role(role_id)
        return Response(status_code=status.HTTP_200_OK)
    except RoleNotFoundError:
        raise RoleNotFoundHttpError()
    except ProtectedRoleError:
        raise ProtectedRoleHttpError()


@router.patch("/{role_id}")
async def modify_role(
    role_id: UUID4,
    modify_role_data: UpdateRoleIn,
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> Response:
    try:
        await role_service.modify_role(role_id, modify_role_data)
        return Response(status_code=status.HTTP_200_OK)
    except RoleNotFoundError:
        raise RoleNotFoundHttpError()
    except RoleAlreadyExistsError:
        raise RoleAlreadyExistsHttpError()
    except ProtectedRoleError:
        raise ProtectedRoleHttpError()


@router.post("/assign")
async def assign_role(
    assign_role_data: AssignRoleIn,
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> Response:
    try:
        await role_service.assign_role(assign_role_data)
        return Response(status_code=status.HTTP_200_OK)
    except RoleNotFoundError:
        raise RoleNotFoundHttpError()
    except UserNotFoundError:
        raise UserNotFoundHttpError()


@router.post("/revoke")
async def revoke_role(
    revoke_role_data: RevokeRoleIn,
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> Response:
    try:
        await role_service.revoke_role(revoke_role_data.user_id)
        return Response(status_code=status.HTTP_200_OK)
    except UserNotFoundError:
        raise UserNotFoundHttpError()
