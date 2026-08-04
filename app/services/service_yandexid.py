from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any, ClassVar
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import pydantic
from opentelemetry import trace
from redis import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.core.config import yandexid_settings
from app.core.enums import OAuthProvider
from app.core.logging import log_handled_exception
from app.db.clients import redis
from app.db.helpers import get_or_create_default_role
from app.db.models import OAuthAccount, User
from app.schemas.misc import DeviceInfo, RequestMeta
from app.schemas.yandexid import (
    YandexIdAuthorizeParams,
    YandexIdCodeVerifier,
    YandexIdTokenData,
    YandexIdTokenRequestData,
    YandexIdUserData,
    YandexIdUserRequestParams,
)

from .helpers import build_login_history, issue_token_pair
from .service_base import BaseService

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class YandexIdStateError(Exception):
    pass


class YandexIdTokenError(Exception):
    pass


class YandexIdProviderError(Exception):
    pass


class YandexIdUserInfoError(Exception):
    pass


class YandexIdAccountConflictError(Exception):
    pass


class YandexIdService(BaseService):
    _STATE_CACHE_PREFIX: ClassVar[str] = f"oauth:{OAuthProvider.YANDEX}:state"
    _PKCE_METHOD: ClassVar[str] = "S256"
    _PKCE_VERIFIER_NBYTES: ClassVar[int] = 64

    @staticmethod
    def _state_cache_key(state: UUID | str) -> str:
        return f"{YandexIdService._STATE_CACHE_PREFIX}:{state}"

    async def build_login_redirect(self, state: UUID) -> str:
        with tracer.start_as_current_span("auth.oauth.start") as span:
            code_verifier = self._generate_code_verifier()
            login_params = self._build_login_params(state, code_verifier)
            span.set_attribute("auth.provider", OAuthProvider.YANDEX.value)
            span.set_attribute("auth.oauth.state_created", True)

            try:
                await redis.setex(
                    self._state_cache_key(login_params.state),
                    yandexid_settings.confirmation_code_ttl,
                    json.dumps({"code_verifier": code_verifier}),
                )
            except RedisError as exc:
                log_handled_exception(
                    logger, "Failed to initialize Yandex authorization state", exc
                )
                span.set_attribute("auth.result", "provider_error")
                raise YandexIdProviderError(
                    "Failed to initialize Yandex authorization state"
                ) from exc

            query = urlencode(
                login_params.model_dump(
                    mode="json",
                    exclude_none=True,
                )
            )
            span.set_attribute("auth.result", "success")
            return f"{yandexid_settings.auth_url}?{query}"

    async def authorize(
        self, code: str, state: UUID, request_meta: RequestMeta, device_info: DeviceInfo
    ):
        with tracer.start_as_current_span("auth.oauth.callback") as span:
            span.set_attribute("auth.provider", OAuthProvider.YANDEX.value)
            cached_state = await self._consume_cached_state(state=state)
            span.set_attribute("auth.oauth.state_valid", True)

            token_data = await self._exchange_code(
                code=code,
                code_verifier=cached_state.code_verifier,
                device_info=device_info,
            )
            user_data = await self._fetch_user_info(access_token=token_data.access_token)
            user = await self._resolve_user(user_data)
            tokens = issue_token_pair(user)
            try:
                self.session.add(
                    build_login_history(
                        user_id=user.id,
                        request_meta=request_meta,
                        device_info=device_info,
                    )
                )
                await self.session.commit()
            except Exception as exc:  # noqa: BLE001 - non-critical audit trail
                log_handled_exception(logger, "Failed to persist Yandex login history", exc)
                await self.session.rollback()
            span.set_attribute("auth.result", "success")
            return tokens

    def _build_login_params(
        self, state: UUID, code_verifier: str | None = None
    ) -> YandexIdAuthorizeParams:
        params: dict[str, Any] = {
            "client_id": yandexid_settings.client_id,
            "state": state,
            "redirect_uri": yandexid_settings.redirect_url,
            "code_verifier": code_verifier,
            "code_challenge": (
                self._generate_code_challenge(code_verifier) if code_verifier else None
            ),
            "code_challenge_method": self._PKCE_METHOD if code_verifier else None,
        }
        return YandexIdAuthorizeParams.model_validate(params)

    @staticmethod
    def _device_info_from_params(login_params: YandexIdAuthorizeParams) -> DeviceInfo | None:
        if login_params.device_id is None:
            return None
        return DeviceInfo(
            device_id=login_params.device_id,
            device_name=login_params.device_name,
        )

    async def _consume_cached_state(self, state: UUID) -> YandexIdCodeVerifier:
        try:
            payload = await redis.getdel(self._state_cache_key(state))
        except RedisError as exc:
            log_handled_exception(logger, "Failed to validate Yandex authorization state", exc)
            raise YandexIdProviderError("Failed to validate Yandex authorization state") from exc
        if payload is None:
            raise YandexIdStateError("Yandex authorization state is invalid or expired")
        try:
            return YandexIdCodeVerifier.model_validate_json(payload)
        except pydantic.ValidationError as exc:
            log_handled_exception(logger, "Yandex authorization state payload is invalid", exc)
            raise YandexIdStateError("Yandex authorization state payload is invalid") from exc

    async def _exchange_code(
        self,
        code: str,
        code_verifier: str,
        device_info: DeviceInfo | None = None,
    ) -> YandexIdTokenData:
        with tracer.start_as_current_span("auth.oauth.token_exchange") as span:
            payload = YandexIdTokenRequestData(
                code=code,
                code_verifier=code_verifier,
                device_id=device_info.device_id if device_info else None,
                device_name=device_info.device_name if device_info else None,
            )
            try:
                timeout = yandexid_settings.http_timeout_seconds
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        yandexid_settings.token_url,
                        data=payload.model_dump(exclude_none=True),
                        headers={"Authorization": yandexid_settings.auth_header},
                    )
            except httpx.RequestError as exc:
                log_handled_exception(logger, "Failed to request Yandex token", exc)
                span.set_attribute("auth.result", "provider_request_error")
                raise YandexIdTokenError("Error during Yandex token exchange request") from exc

            response_data = self._safe_json(response)
            span.set_attribute("auth.oauth.token_status", response.status_code)
            if response.is_error:
                logger.warning(
                    "Yandex token exchange failed status=%s error=%s",
                    response.status_code,
                    response_data.get("error"),
                )
                span.set_attribute("auth.result", "provider_request_error")
                raise YandexIdTokenError("Yandex token exchange failed")

            try:
                token_data = YandexIdTokenData.model_validate(response_data)
            except pydantic.ValidationError as exc:
                log_handled_exception(logger, "Yandex token response payload is invalid", exc)
                span.set_attribute("auth.result", "invalid_response_payload")
                raise YandexIdProviderError("Yandex token response payload is invalid") from exc
            span.set_attribute("auth.result", "success")
            return token_data

    async def _fetch_user_info(self, access_token: str) -> YandexIdUserData:
        with tracer.start_as_current_span("auth.oauth.user_info") as span:
            params = YandexIdUserRequestParams().model_dump(exclude_none=True)
            try:
                timeout = yandexid_settings.http_timeout_seconds
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.get(
                        yandexid_settings.user_info_url,
                        params=params,
                        headers={"Authorization": f"OAuth {access_token}"},
                    )
            except httpx.RequestError as exc:
                log_handled_exception(logger, "Failed to request Yandex user info", exc)
                span.set_attribute("auth.result", "provider_request_error")
                raise YandexIdUserInfoError("Error during Yandex user info request") from exc

            response_data = self._safe_json(response)
            span.set_attribute("auth.oauth.user_info_status", response.status_code)
            if response.is_error:
                logger.warning(
                    "Yandex user info failed status=%s error=%s",
                    response.status_code,
                    response_data.get("error"),
                )
                span.set_attribute("auth.result", "provider_request_error")
                raise YandexIdUserInfoError("Yandex user info request returned an error")
            try:
                user_data = YandexIdUserData.model_validate(response_data)
            except pydantic.ValidationError as exc:
                log_handled_exception(logger, "Yandex user info response payload is invalid", exc)
                span.set_attribute("auth.result", "invalid_response_payload")
                raise YandexIdUserInfoError("Yandex user info response payload is invalid") from exc
            span.set_attribute("auth.result", "success")
            return user_data

    async def _resolve_user(self, yandex_user_data: YandexIdUserData) -> User:
        with tracer.start_as_current_span("auth.oauth.user_resolve") as span:
            provider = OAuthProvider.YANDEX.value
            provider_user_id = str(yandex_user_data.id)

            linked_stmt = (
                select(User)
                .join(OAuthAccount, OAuthAccount.user_id == User.id)
                .options(joinedload(User.role))
                .where(
                    OAuthAccount.provider == provider,
                    OAuthAccount.provider_user_id == provider_user_id,
                )
            )
            linked_result = await self.session.execute(linked_stmt)
            linked_user = linked_result.scalars().first()
            if linked_user:
                span.set_attribute("auth.oauth.user_acquire_method", "existing_link")
                return linked_user

            existing_user = await self.get_user_by_email(
                yandex_user_data.default_email, with_role=True
            )
            if existing_user:
                linked = await self._attach_oauth_account(
                    user=existing_user,
                    provider=provider,
                    provider_user_id=provider_user_id,
                )
                span.set_attribute("auth.oauth.user_acquire_method", "autolink_existing_email")
                return linked

            default_role = await get_or_create_default_role()
            new_user = User(
                email=yandex_user_data.default_email,
                first_name=yandex_user_data.first_name,
                last_name=yandex_user_data.last_name,
                password_hash=self.get_password_hash(str(uuid4())),
                role_id=default_role.id,
            )
            self.session.add(new_user)
            await self.session.flush()
            created_user = await self._attach_oauth_account(
                user=new_user,
                provider=provider,
                provider_user_id=provider_user_id,
            )
            loaded_user = await self.get_user_by_id(str(created_user.id), load_role=True)
            span.set_attribute("auth.oauth.user_acquire_method", "create_new_user")
            return loaded_user  # pyright: ignore[reportReturnType]

    async def _attach_oauth_account(
        self,
        user: User,
        provider: str,
        provider_user_id: str,
    ) -> User:
        self.session.add(
            OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
            )
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            log_handled_exception(logger, "Yandex account link conflict (integrity)", exc)
            await self.session.rollback()
            raise YandexIdAccountConflictError("Yandex account link conflict") from exc
        await self.session.refresh(user)
        return user

    @staticmethod
    def _safe_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            log_handled_exception(logger, "Failed to parse Yandex response as JSON", exc)
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _generate_code_verifier(cls) -> str:
        return secrets.token_urlsafe(cls._PKCE_VERIFIER_NBYTES)

    @staticmethod
    def _generate_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
