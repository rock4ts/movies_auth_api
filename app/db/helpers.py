import logging

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import DEFAULT_ROLE_ACCESS_LABELS, DEFAULT_ROLE_TITLE

from .clients import async_session, engine
from .models import ProjectBase, Role, User

logger = logging.getLogger(__name__)
password_hash = PasswordHash.recommended()


async def get_or_create_default_role() -> Role:
    async with async_session() as session:
        result = await session.execute(select(Role).where(Role.title == DEFAULT_ROLE_TITLE))
        role = result.scalars().first()
        if role:
            return role

        role = Role(title=DEFAULT_ROLE_TITLE, access_labels=list(DEFAULT_ROLE_ACCESS_LABELS))
        session.add(role)
        await session.commit()
        return role


async def drop_all_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(ProjectBase.metadata.drop_all)


async def create_all_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(ProjectBase.metadata.create_all)


async def create_superuser(email: str, password: str):
    async with async_session() as session:
        user_checkq = await session.execute(select(User).where(User.email == email))
        user_exists = user_checkq.scalars().first()
        if user_exists:
            logger.info(f"Пользователь с email {email} уже существует")
            return

        user = User(
            email=email,
            password_hash=password_hash.hash(password),
            is_superuser=True,
            role_id=None,
        )
        session.add(user)
        try:
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.warning(f"Ошибка при создании суперпользователя: {str(e)}")
