import logging

import sqlalchemy.exc as sa_exc
from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log_handled_exception
from app.db.helpers import DEFAULT_ROLE_TITLE, get_or_create_default_role
from app.db.models import Role, User
from app.schemas.role import AssignRoleIn, ReadRoleOut, RoleCreateIn, RoleCreateOut, UpdateRoleIn

from .service_base import UserNotFoundError

logger = logging.getLogger(__name__)


class RoleAlreadyExistsError(Exception):
    pass


class RoleNotFoundError(Exception):
    pass


class ProtectedRoleError(Exception):
    pass


class RoleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_role(self, role_data_in: RoleCreateIn) -> RoleCreateOut:
        try:
            role = Role(title=role_data_in.title, access_labels=role_data_in.access_labels)
            self.session.add(role)
            await self.session.commit()
            return RoleCreateOut.model_validate(role, from_attributes=True)
        except sa_exc.IntegrityError as exc:
            log_handled_exception(logger, "Role already exists (integrity)", exc)
            await self.session.rollback()
            raise RoleAlreadyExistsError() from None

    async def remove_role(self, role_id: UUID4) -> None:
        role = await self.session.get(Role, role_id)
        if not role:
            raise RoleNotFoundError()
        if role.title == DEFAULT_ROLE_TITLE:
            raise ProtectedRoleError()
        await self.session.delete(role)
        await self.session.commit()

    async def modify_role(self, role_id: UUID4, modify_role_data: UpdateRoleIn) -> None:
        role = await self.session.get(Role, role_id)
        if not role:
            raise RoleNotFoundError()
        if role.title == DEFAULT_ROLE_TITLE and modify_role_data.title != DEFAULT_ROLE_TITLE:
            raise ProtectedRoleError()
        role.title = modify_role_data.title
        role.access_labels = modify_role_data.access_labels
        try:
            await self.session.commit()
        except sa_exc.IntegrityError as exc:
            log_handled_exception(logger, "Role title conflict (integrity)", exc)
            await self.session.rollback()
            raise RoleAlreadyExistsError() from None

    async def get_all_roles(self) -> list[ReadRoleOut]:
        roles = await self.session.execute(select(Role))
        return [
            ReadRoleOut.model_validate(role, from_attributes=True) for role in roles.scalars().all()
        ]

    async def assign_role(self, assign_role_data: AssignRoleIn) -> None:
        user = await self.session.get(User, assign_role_data.user_id)
        if not user:
            raise UserNotFoundError()
        role = await self.session.get(Role, assign_role_data.role_id)
        if not role:
            raise RoleNotFoundError()
        user.role_id = assign_role_data.role_id
        await self.session.commit()

    async def revoke_role(self, user_id: UUID4) -> None:
        user = await self.session.get(User, user_id)
        if not user:
            raise UserNotFoundError()
        if user.is_superuser:
            user.role_id = None
            await self.session.commit()
            return

        default_role = await get_or_create_default_role()
        user.role_id = default_role.id
        await self.session.commit()
