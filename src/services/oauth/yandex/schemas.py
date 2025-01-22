import uuid
from typing import Mapping

from pydantic import UUID4, BaseModel, EmailStr, HttpUrl

from schemas.token import TokenInfo


class HttpRequestComponents(BaseModel):
    url: HttpUrl
    params: Mapping | None = None
    data: Mapping | None = None
    headers: dict | None = None


class YandexIdLoginRequestParams(BaseModel):
    client_id: str
    response_type: str = "code"
    force_confirm: bool = True
    state: UUID4 = uuid.uuid4()
    device_id: UUID4 | None = None
    device_name: str | None = None
    redirect_uri: HttpUrl | None = None
    login_hint: str | None = None
    scope: str | None = None
    optional_scope: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None


class YandexIdTokenRequestData(BaseModel):
    grant_type: str = "authorization_code"
    code: str
    device_id: UUID4 | None = None
    device_name: str | None = None
    code_verifier: str | None = None


class YandexIdTokenData(BaseModel):
    token_type: str
    access_token: str
    expires_in: int
    refresh_token: str
    scope: str | None = None


class YandexIdUserRequestParams(BaseModel):
    format: str = "json"


class YandexIdUserPhoneNumber(BaseModel):
    id: int
    number: str


class YandexIdUserData(BaseModel):
    login: str
    id: int | str  # Уникальный идентификатор пользователя Яндекса.
    client_id: str
    psuid: str  # Идентификатор авторизованного пользователя в Яндексе. Формируется на стороне Яндекса на основе пары client_id и user_id
    default_email: EmailStr
    default_phone: YandexIdUserPhoneNumber | None
    first_name: str
    last_name: str
    display_name: str
    real_name: str
    sex: str
    real_name: str


class ReconcileYandexIdUserData(YandexIdTokenData):
    default_email: EmailStr


class YandexIdLoginServiceOutput(BaseModel):
    tokens: TokenInfo | None = None
    user_email: EmailStr | None = None
