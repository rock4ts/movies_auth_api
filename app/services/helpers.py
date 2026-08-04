from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from sqlalchemy import inspect
from sqlalchemy.orm.attributes import NO_VALUE

from app.core.config import jwt_settings
from app.core.enums import AccessLabel
from app.db.models import LoginHistory, User
from app.schemas.auth import AccessTokenPayload, RefreshTokenPayload, TokenData
from app.schemas.misc import DeviceInfo, RequestMeta


def _resolve_role_claims(user: User) -> tuple[str | None, list[AccessLabel]]:
    role_attr = inspect(user).attrs.role
    if role_attr.loaded_value is NO_VALUE:
        raise ValueError("User role must be eagerly loaded before creating an access token")

    role = role_attr.loaded_value
    if role is None:
        if user.is_superuser:
            return None, []
        raise ValueError("Non-superuser users must have a role before creating an access token")

    return role.title, role.access_labels


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    role_title, access_labels = _resolve_role_claims(user)
    payload = AccessTokenPayload(
        type="access",
        sub=user.id,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=jwt_settings.access_token_expire_minutes)).timestamp()),
        jti=uuid4(),
        tv=user.token_version,
        is_superuser=user.is_superuser,
        role=role_title,
        access_labels=access_labels,
    ).model_dump(mode="json")
    return jwt.encode(payload, jwt_settings.private_key, algorithm=jwt_settings.algorithm)


def create_refresh_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = RefreshTokenPayload(
        type="refresh",
        sub=user.id,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(days=jwt_settings.refresh_token_expire_days)).timestamp()),
        jti=uuid4(),
        tv=user.token_version,
    ).model_dump(mode="json")
    return jwt.encode(payload, jwt_settings.private_key, algorithm=jwt_settings.algorithm)


def issue_token_pair(user: User) -> TokenData:
    return TokenData(
        access=create_access_token(user),
        refresh=create_refresh_token(user),
    )


def build_login_history(
    user_id: UUID,
    request_meta: RequestMeta,
    device_info: DeviceInfo | None = None,
) -> LoginHistory:
    return LoginHistory(
        user_id=user_id,
        ip_address=request_meta.ip_address or "unknown",
        user_agent=request_meta.user_agent[:500] if request_meta.user_agent else None,
        device_id=str(device_info.device_id) if device_info else None,
    )
