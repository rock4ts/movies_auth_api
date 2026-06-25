from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import User
from app.db.helpers import password_hash


class UserNotFoundError(Exception):
    pass


class BaseService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_email(self, email: str, with_role: bool = False) -> User | None:
        stmt = select(User).where(User.email == email)
        if with_role:
            stmt = stmt.options(joinedload(User.role))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_user_by_id(self, user_id: str, load_role: bool = False) -> User | None:
        stmt = select(User).where(User.id == user_id)
        if load_role:
            stmt = stmt.options(joinedload(User.role))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def get_password_hash(password: str) -> str:
        return password_hash.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return password_hash.verify(plain_password, hashed_password)
