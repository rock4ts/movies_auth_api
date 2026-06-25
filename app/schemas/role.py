from pydantic import UUID4, BaseModel

from app.core.enums import AccessLabel


class RoleCreateIn(BaseModel):
    title: str
    access_labels: list[AccessLabel]


class RoleCreateOut(BaseModel):
    id: UUID4
    title: str
    access_labels: list[AccessLabel]


class UpdateRoleIn(RoleCreateIn): ...


class ReadRoleOut(RoleCreateOut): ...


class AssignRoleIn(BaseModel):
    role_id: UUID4
    user_id: UUID4


class RevokeRoleIn(BaseModel):
    user_id: UUID4
