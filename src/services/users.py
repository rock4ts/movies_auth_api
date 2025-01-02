from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload

from models import User
from schemas.user import UserIn, UserLogin


async def create_user(
        user_create: UserIn,
        session: AsyncSession,
) -> User:
    user = User(**user_create.model_dump())
    user.set_password(user_create.password)
    session.add(user)
    await session.commit()
    return user


async def get_user_by_email(
        email: str,
        session: AsyncSession,
) -> User | None:
    result = await session.execute(
        select(User).where(User.email == email).options(joinedload(User.role))
    )
    user = result.scalars().first()
    return user


async def validate_auth_user_login(
        user: UserLogin,
        session: AsyncSession,
) -> User:
    email, password = user.email, user.password
    unauth_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid username or password"
    )
    if not (user := await get_user_by_email(email, session=session)):
        raise unauth_exc
    if not user.check_password(password):
        raise unauth_exc
    return user
