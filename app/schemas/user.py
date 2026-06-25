from datetime import datetime

from pydantic import UUID4, BaseModel, EmailStr, Field
from .role import ReadRoleOut


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str


class UserCreateOut(BaseModel):
    id: UUID4
    email: EmailStr
    created_at: datetime


class UserChangeEmailIn(BaseModel):
    email: EmailStr
    password: str


class UserChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class UserReadOut(BaseModel):
    id: UUID4
    email: EmailStr
    created_at: datetime
    updated_at: datetime
    role: ReadRoleOut | None = None


class LoginDataOut(BaseModel):
    ip_address: str
    user_agent: str | None = None
    device_id: str | None = None
    logged_in_at: datetime
