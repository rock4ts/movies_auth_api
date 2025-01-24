import logging

import sqlalchemy.exc as sa_exc
from pydantic import UUID4

import models
from db.repository import AsyncBaseRepository
from schemas.role import CreateRoleDTO, UpdateRoleDTO
from services.enums import ServiceWorkResults

logger = logging.getLogger(__name__)


class RoleService:

    @staticmethod
    async def create_role(
        role_dto: CreateRoleDTO, repository: AsyncBaseRepository
    ) -> tuple[ServiceWorkResults, models.Role | None, str | None]:
        try:
            role_obj = models.Role(title=role_dto.title)
            db_role = await repository.add(role_obj)
            return ServiceWorkResults.SUCCESS, db_role, "ok"
        except sa_exc.IntegrityError as e:
            logger.error(f"IntegrityError: {e}")
            return (
                ServiceWorkResults.FAIL,
                f'Role with title "{role_obj.title}" already exist',
                None,
            )
        except sa_exc.SQLAlchemyError as e:
            logger.exception(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None, None

    @staticmethod
    async def remove_role(
        role_id: UUID4, repository: AsyncBaseRepository
    ) -> tuple[ServiceWorkResults, str | None]:
        try:
            result = await repository.delete(models.Role, models.Role.id, [role_id])
            if result.rowcount == 0:
                return ServiceWorkResults.FAIL, f"No role found for ID {role_id}."
            return ServiceWorkResults.SUCCESS, "ok"
        except sa_exc.IntegrityError as e:
            logger.exception(f"IntegrityError: {e}")
            return ServiceWorkResults.FAIL, "Delete operation is not allowed on system-level roles"
        except sa_exc.SQLAlchemyError as e:
            logger.exception(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None

    @staticmethod
    async def modify_role(
        role_id: UUID4, role_dto: UpdateRoleDTO, repository: AsyncBaseRepository
    ) -> tuple[ServiceWorkResults, str | None]:
        try:
            role_data = role_dto.model_dump()
            await repository.update(models.Role, [models.Role.id == role_id,], role_data)
            return ServiceWorkResults.SUCCESS, "ok"
        except sa_exc.NoResultFound as e:
            logger.exception(f"NoResultFound: {e}")
            return ServiceWorkResults.FAIL, f"No role found for ID {role_id}."
        except sa_exc.IntegrityError as e:
            logger.exception(f"IntegrityError: {e}")
            return (
                ServiceWorkResults.FAIL,
                f'Role for ID {role_id} could not be updated: "title" must be unique.',
            )
        except sa_exc.SQLAlchemyError as e:
            logger.exception(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None

    @staticmethod
    async def get_all_roles(
        repository: AsyncBaseRepository,
    ) -> tuple[ServiceWorkResults, list[models.Role] | None]:
        try:
            db_roles = await repository.list(models.Role)
            return ServiceWorkResults.SUCCESS, db_roles
        except sa_exc.SQLAlchemyError as e:
            logger.exception(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None

    @staticmethod
    async def assign_role(
        role_id: UUID4, user_id: UUID4, repository: AsyncBaseRepository
    ) -> tuple[ServiceWorkResults, str | None]:
        try:
            await repository.update(
                models.User, [models.User.id == user_id,], {models.User.role_id.name: role_id}
            )
            return ServiceWorkResults.SUCCESS, "ok"
        except sa_exc.NoResultFound as e:
            logger.error(f"NoResultFound: {e}")
            return ServiceWorkResults.FAIL, f"No user found for ID {user_id}"
        except sa_exc.IntegrityError as e:
            logger.error(f"IntegrityError: {e}")
            return ServiceWorkResults.FAIL, f"No role found for ID {user_id}"
        except sa_exc.SQLAlchemyError as e:
            logger.error(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None

    @staticmethod
    async def revoke_role(
        user_id: UUID4, repository: AsyncBaseRepository
    ) -> tuple[ServiceWorkResults, str | None]:
        try:
            await repository.update(
                models.User, [models.User.id == user_id,], {models.User.role_id.name: None}
            )
            return ServiceWorkResults.SUCCESS, "ok"
        except sa_exc.NoResultFound as e:
            logger.error(f"NoResultFound: {e}")
            return ServiceWorkResults.FAIL, f"No user found for ID {user_id}"
        except sa_exc.SQLAlchemyError as e:
            logger.error(f"Database error: {e}")
            return ServiceWorkResults.ERROR, None
