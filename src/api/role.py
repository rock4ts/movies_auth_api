from async_fastapi_jwt_auth.auth_jwt import AuthJWTBearer
from fastapi import APIRouter
from fastapi.params import Depends
from pydantic import UUID4


import models
from api.exceptions import Http400, Http500
from db.repository import AsyncBaseRepository
from schemas.role import CreateRoleDTO, ReadRoleDTO, ReadRoleDTO, UpdateRoleDTO
from services.enums import ServiceWorkResults
from services.role import RoleService
from .dependencies import (
    check_invalid_token,
    check_superuser,
    get_role_service,
    get_sqlalchemy_repository,
)

auth_bearer = AuthJWTBearer()
router = APIRouter(
    dependencies=[
        Depends(auth_bearer),
        Depends(check_invalid_token),
        Depends(check_superuser),
    ]
)


@router.post("/create", response_model=ReadRoleDTO)
async def create_role(
    role_dto: CreateRoleDTO,
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> models.Role:

    result, db_role, res_msg = await role_service.create_role(role_dto, repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return db_role


@router.delete("/delete/{role_id}")
async def delete_role(
    role_id: UUID4,
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> str:

    result, res_msg = await role_service.remove_role(role_id, repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return res_msg


@router.post("/update/{role_id}")
async def update_role(
    role_id: UUID4,
    role_dto: UpdateRoleDTO,
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> str:

    result, res_msg = await role_service.modify_role(role_id, role_dto, repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return res_msg


@router.get("/list", response_model=list[ReadRoleDTO])
async def list_roles(
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> list[models.Role]:

    result, db_roles = await role_service.get_all_roles(repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500

    return db_roles


@router.post("/{role_id}/assign/{user_id}")
async def assign_role(
    role_id: UUID4,
    user_id: UUID4,
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> str:

    result, res_msg = await role_service.assign_role(role_id, user_id, repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return res_msg


@router.post("/revoke/{user_id}")
async def revoke_role(
    user_id: UUID4,
    role_service: RoleService = Depends(get_role_service),
    repository: AsyncBaseRepository = Depends(get_sqlalchemy_repository),
) -> str:

    result, res_msg = await role_service.revoke_role(user_id, repository)
    if result is ServiceWorkResults.ERROR:
        raise Http500
    if result is ServiceWorkResults.FAIL:
        raise Http400(res_msg)

    return res_msg
