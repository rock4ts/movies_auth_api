from typing import Dict, List
from redis.asyncio import Redis

from async_fastapi_jwt_auth import AuthJWT
from async_fastapi_jwt_auth.auth_jwt import AuthJWTBearer
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import UUID4
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from db.redis import get_redis_connection
from models.history import LoginHistory
from models.user import User
from schemas.user import UserLogin, UserUpdate
from schemas.account import LoginHistoryResponse
from services.account import account_page as service_account_page
from services.token import check_invalid_token
from .dependencies import get_session

router = APIRouter()
auth_bearer = AuthJWTBearer()


@router.patch("/update")
async def update_user(
        user_update: UserUpdate,
        session: AsyncSession = Depends(get_session),
        authorize: AuthJWT = Depends(auth_bearer),
        redis: Redis = Depends(get_redis_connection)
) -> dict:
    """
    Эндпоинт для изменения почты или пароля
    """

    await authorize.jwt_required()
    token = await authorize.get_raw_jwt()
    if await check_invalid_token(token, redis):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid"
        )

    user_id: UUID4 = await authorize.get_jwt_subject()

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=400, detail="User not found")

    # Проверка уникальности email
    if user.email != user_update.email:
        result = await session.execute(
            select(User).where(User.email == user_update.email)
        )
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already in use")

    # Обновление данных
    user.email = user_update.email
    user.set_password(user_update.password)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=400, detail="Error updating user information"
        )

    return {"detail": "User information updated successfully"}


@router.get("/me", response_model=UserLogin)
async def account_page(
    session: AsyncSession = Depends(get_session),
    authorize: AuthJWT = Depends(auth_bearer),
    redis: Redis = Depends(get_redis_connection),
) -> UserLogin:
    """
    Эндпоинт для страницы Личный кабинет
    Доступен только для аутентифицированных юзеров
    Достает id из JWT токена, и возвращает модель
    """
    try:
        await authorize.jwt_required()

        token = await authorize.get_raw_jwt()
        if await check_invalid_token(token, redis):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalid"
            )

        user_id: UUID4 = await authorize.get_jwt_subject()
    except Exception:
        raise HTTPException(status_code=401, detail="Refresh token invalid")
    user: UserLogin = await service_account_page(user_id, session)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/history", response_model=LoginHistoryResponse)
async def get_login_history(
        authorize: AuthJWT = Depends(auth_bearer),
        session: AsyncSession = Depends(get_session),
        redis: Redis = Depends(get_redis_connection),
        page: int = Query(1, ge=1, description="Номер страницы"),
        page_size: int = Query(
            10, ge=1, le=100, description="Размер страницы"
        ),
) -> LoginHistoryResponse:
    """
    Эндпоинт для просмотра истории входов пользователя
    """
    try:
        await authorize.jwt_required()

        token = await authorize.get_raw_jwt()
        if await check_invalid_token(token, redis):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalid"
            )

        user_id: UUID4 = await authorize.get_jwt_subject()

        total_count_query = select(
            func.count(LoginHistory.id)
        ).where(LoginHistory.user_id == user_id)
        total_count = (await session.execute(total_count_query)).scalar()

        query = (
            select(LoginHistory)
            .where(LoginHistory.user_id == user_id)
            .order_by(LoginHistory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await session.execute(query)
        login_history = result.scalars().all()

        history_data = [{
            "date_time": lh.created_at.strftime('%a %d %b %Y, %I:%M%p'),
            "ip_address": lh.ip_address,
            "user-agent": lh.user_agent
        } for lh in login_history]

        return {
            "data": history_data,
            "meta": {
                "current_page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Token invalid")
