from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status, Query

from app.db.models import User
from app.schemas.user import (
    LoginDataOut,
    UserChangeEmailIn,
    UserChangePasswordIn,
    UserCreateIn,
    UserCreateOut,
    UserReadOut,
)

from app.services.service_base import UserNotFoundError
from app.services.service_user import (
    EmailAlreadyExistsError,
    UserAlreadyExistsError,
    UserService,
    WrongPasswordError,
)
from .dependencies import get_token_user, get_user_service, rate_limit_route_by_ip
from .exceptions import UserNotFoundHttpError, WrongPasswordHttpError

router = APIRouter()


@router.post("")
async def create_user(
    user_data: UserCreateIn,
    _rate_limited: Annotated[None, Depends(rate_limit_route_by_ip)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserCreateOut:
    try:
        user = await user_service.create_user(user_data=user_data)
    except UserAlreadyExistsError:
        raise HTTPException(status_code=400, detail="User already exists")
    return UserCreateOut.model_validate(user, from_attributes=True)


@router.get("/me")
async def user_info(
    user: Annotated[User, Depends(get_token_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
) -> UserReadOut:
    try:
        user = await user_service.get_user_info(user_id=user.id)
        return UserReadOut.model_validate(user, from_attributes=True)
    except UserNotFoundError:
        raise UserNotFoundHttpError()


@router.patch("/me/email")
async def change_email(
    change_email_data: UserChangeEmailIn,
    user: Annotated[User, Depends(get_token_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    try:
        await user_service.change_email(change_email_data=change_email_data, user=user)
    except WrongPasswordError:
        raise WrongPasswordHttpError()
    except EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email already exists")
    return Response(status_code=status.HTTP_200_OK)


@router.patch("/me/password")
async def change_password(
    change_password_data: UserChangePasswordIn,
    user: Annotated[User, Depends(get_token_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    try:
        await user_service.change_password(change_password_data=change_password_data, user=user)
    except WrongPasswordError:
        raise WrongPasswordHttpError()
    return Response(status_code=status.HTTP_200_OK)


@router.get("/me/login-history")
async def get_login_history(
    user: Annotated[User, Depends(get_token_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int, Query(ge=1, description="Номер страницы")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Размер страницы")] = 10,
) -> list[LoginDataOut]:
    return await user_service.get_login_history(user_id=user.id, page=page, page_size=page_size)
