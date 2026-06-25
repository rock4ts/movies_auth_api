import logging

from pydantic import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from opentelemetry import trace

from app.core.logging import log_handled_exception
from app.db.models import LoginHistory, User
from app.schemas.user import (
    LoginDataOut,
    UserChangeEmailIn,
    UserChangePasswordIn,
    UserCreateIn,
)
from app.db.helpers import get_or_create_default_role
from .service_base import BaseService, UserNotFoundError

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class UserAlreadyExistsError(Exception):
    pass


class WrongPasswordError(Exception):
    pass


class EmailAlreadyExistsError(Exception):
    pass


class UserService(BaseService):
    async def create_user(self, user_data: UserCreateIn) -> User:
        with tracer.start_as_current_span("auth.user_create") as span:
            existing_user = await self.get_user_by_email(user_data.email)
            if existing_user:
                span.set_attribute("auth.result", "already_exists")
                raise UserAlreadyExistsError("User with this username or email already exists")

            password_hash = self.get_password_hash(user_data.password)
            default_role = await get_or_create_default_role()
            user = User(
                email=user_data.email,
                password_hash=password_hash,
                role_id=default_role.id,
            )
            try:
                self.session.add(user)
                await self.session.commit()
            except IntegrityError as exc:
                log_handled_exception(logger, "User already exists (integrity)", exc)
                await self.session.rollback()
                span.set_attribute("auth.result", "already_exists")
                raise UserAlreadyExistsError("User with this username or email already exists")
            await self.session.refresh(user)
            span.set_attribute("auth.result", "success")
            return user

    async def change_email(self, change_email_data: UserChangeEmailIn, user: User) -> None:
        if not self.verify_password(
            change_email_data.password,
            user.password_hash,
        ):
            raise WrongPasswordError("Wrong password")
        user.email = change_email_data.email
        try:
            await self.session.commit()
        except IntegrityError as exc:
            log_handled_exception(logger, "Email already exists (integrity)", exc)
            await self.session.rollback()
            raise EmailAlreadyExistsError("User with this email already exists")

    async def change_password(
        self,
        change_password_data: UserChangePasswordIn,
        user: User,
    ) -> None:
        if not self.verify_password(
            change_password_data.old_password,
            user.password_hash,
        ):
            raise WrongPasswordError("Wrong current password")
        user.password_hash = self.get_password_hash(change_password_data.new_password)
        user.token_version += 1
        await self.session.commit()

    async def get_login_history(
        self, user_id: UUID4, page: int, page_size: int
    ) -> list[LoginDataOut]:
        query = (
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.logged_in_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        login_history = result.scalars().all()
        return [LoginDataOut.model_validate(lh, from_attributes=True) for lh in login_history]

    async def get_user_info(self, user_id: UUID4) -> User:
        user = await self.get_user_by_id(str(user_id), load_role=True)
        if not user:
            raise UserNotFoundError("User not found")
        return user
