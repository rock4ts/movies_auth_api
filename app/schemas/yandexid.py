from typing import Literal

from pydantic import BaseModel, EmailStr, HttpUrl, UUID4


class YandexIdAuthorizeParams(BaseModel):
    response_type: Literal["code"] = "code"
    client_id: str
    redirect_uri: HttpUrl
    state: UUID4
    code_challenge: str | None = None
    code_challenge_method: Literal["S256"] | None = "S256"
    force_confirm: Literal["yes"] = "yes"
    device_id: UUID4 | None = None
    device_name: str | None = None
    login_hint: str | None = None
    scope: str | None = None
    optional_scope: str | None = None


class YandexIdCodeVerifier(BaseModel):
    code_verifier: str


class YandexIdTokenRequestData(BaseModel):
    grant_type: Literal["authorization_code"] = "authorization_code"
    code: str
    code_verifier: str
    device_id: UUID4 | None = None
    device_name: str | None = None


class YandexIdTokenData(BaseModel):
    token_type: str
    access_token: str
    expires_in: int
    refresh_token: str
    scope: str | None = None


class YandexIdUserRequestParams(BaseModel):
    format: str | None = "json"


class YandexIdUserPhoneNumber(BaseModel):
    id: int
    number: str


# more data can be requested from the user info endpoint
class YandexIdUserData(BaseModel):
    login: str
    id: int | str  # Уникальный идентификатор пользователя Яндекса.
    client_id: str
    psuid: str  # Идентификатор авторизованного пользователя в Яндексе. Формируется на стороне Яндекса на основе пары client_id и user_id
    default_email: EmailStr
    first_name: str
    last_name: str
    display_name: str
    real_name: str
    sex: str


class ReconcileYandexIdUserData(YandexIdTokenData):
    default_email: EmailStr
