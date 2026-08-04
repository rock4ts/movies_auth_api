import logging
from datetime import UTC, datetime

import jwt
import pydantic
from opentelemetry import trace

from app.core.config import jwt_settings
from app.core.logging import log_handled_exception
from app.db.clients import redis
from app.db.models import User
from app.schemas.auth import RefreshTokenPayload, TokenData, UserLoginData
from app.schemas.misc import DeviceInfo, RequestMeta

from .helpers import build_login_history, issue_token_pair
from .service_base import BaseService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class WrongCredentialsError(Exception):
    def __init__(self, detail: str = "Incorrect email or password"):
        super().__init__(detail)


class RefreshTokenError(Exception):
    pass


class AuthService(BaseService):
    async def login_user(
        self,
        login_data: UserLoginData,
        request_meta: RequestMeta,
        device_info: DeviceInfo | None = None,
    ) -> TokenData:
        with tracer.start_as_current_span("auth.login") as span:
            user = await self.get_user_by_email(login_data.email, with_role=True)
            if not user or not self.verify_password(login_data.password, user.password_hash):
                span.set_attribute("auth.result", "invalid_credentials")
                raise WrongCredentialsError()

            tokens = issue_token_pair(user)
            try:
                login_history = build_login_history(user.id, request_meta, device_info)
                self.session.add(login_history)
                await self.session.commit()
                span.set_attribute("auth.login_history_saved", True)
            except Exception as exc:
                log_handled_exception(logger, "Failed to persist login history", exc)
                await self.session.rollback()
                span.set_attribute("auth.login_history_saved", False)

            span.set_attribute("auth.result", "success")
            return tokens

    async def refresh_tokens(self, refresh_token: str) -> TokenData:
        with tracer.start_as_current_span("auth.refresh") as span:
            try:
                payload = jwt.decode(
                    refresh_token,
                    jwt_settings.public_key,
                    algorithms=[jwt_settings.algorithm],
                )
            except jwt.ExpiredSignatureError as exc:
                log_handled_exception(logger, "Refresh token expired", exc)
                span.set_attribute("auth.result", "expired_token")
                raise RefreshTokenError("Token has expired") from None
            except jwt.InvalidTokenError as exc:
                log_handled_exception(logger, "Invalid refresh token", exc)
                span.set_attribute("auth.result", "invalid_token")
                raise RefreshTokenError("Invalid token") from None

            try:
                payload = RefreshTokenPayload.model_validate(payload)
            except pydantic.ValidationError as exc:
                log_handled_exception(logger, "Invalid refresh token payload", exc)
                span.set_attribute("auth.result", "invalid_payload")
                raise RefreshTokenError("Invalid token payload") from None

            if payload.type != "refresh":
                span.set_attribute("auth.result", "wrong_token_type")
                raise RefreshTokenError("Token is not a refresh token")

            with tracer.start_as_current_span("auth.refresh.blacklist_check") as blacklist_span:
                is_blacklisted = await self.check_blacklisted_token(str(payload.jti))
                blacklist_span.set_attribute("auth.refresh_token_blacklisted", is_blacklisted)

            if is_blacklisted:
                span.set_attribute("auth.result", "blacklisted_token")
                raise RefreshTokenError("Token is invalid")

            user = await self.get_user_by_id(str(payload.sub), load_role=True)
            if not user:
                span.set_attribute("auth.result", "user_not_found")
                raise RefreshTokenError("User not found")

            if payload.tv != user.token_version:
                span.set_attribute("auth.result", "token_version_mismatch")
                raise RefreshTokenError("Token version mismatch")

            with tracer.start_as_current_span("auth.refresh.blacklist_previous"):
                await self.blacklist_token(
                    str(payload.jti),
                    max(1, payload.exp - int(datetime.now(UTC).timestamp())),
                )

            tokens = issue_token_pair(user)
            span.set_attribute("auth.result", "success")
            return tokens

    @staticmethod
    async def check_blacklisted_token(jti: str) -> bool:
        return await redis.get(f"blacklist:{jti}") is not None

    @staticmethod
    async def blacklist_token(jti: str, ttl: int) -> None:
        await redis.setex(f"blacklist:{jti}", ttl, "true")

    async def logout(self, refresh_token: str) -> None:
        with tracer.start_as_current_span("auth.logout") as span:
            try:
                payload_dict = jwt.decode(
                    refresh_token,
                    jwt_settings.public_key,
                    algorithms=[jwt_settings.algorithm],
                )

            except jwt.InvalidTokenError as exc:
                log_handled_exception(logger, "Invalid logout token", exc)
                span.set_attribute("auth.result", "invalid_token")
                raise RefreshTokenError("Invalid token") from None

            try:
                payload = RefreshTokenPayload.model_validate(payload_dict)
            except pydantic.ValidationError as exc:
                log_handled_exception(logger, "Invalid logout token payload", exc)
                span.set_attribute("auth.result", "invalid_payload")
                raise RefreshTokenError("Invalid token payload") from None

            if payload.type != "refresh":
                span.set_attribute("auth.result", "wrong_token_type")
                raise RefreshTokenError("Token is not a refresh token")

            ttl = payload.exp - int(datetime.now(UTC).timestamp())

            if ttl <= 0:
                span.set_attribute("auth.result", "expired_token")
                return

            await self.blacklist_token(str(payload.jti), ttl)
            span.set_attribute("auth.result", "success")

    async def logout_others(self, user: User) -> TokenData:
        with tracer.start_as_current_span("auth.logout_others") as span:
            user.token_version += 1
            await self.session.commit()
            updated_user = await self.get_user_by_id(str(user.id), load_role=True)
            if not updated_user:
                raise WrongCredentialsError("User not found")
            tokens = issue_token_pair(updated_user)
            span.set_attribute("auth.result", "success")
            return tokens
