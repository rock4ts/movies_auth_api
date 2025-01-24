import uuid

from fastapi.params import Depends
from pydantic import UUID4, BaseModel, EmailStr, HttpUrl

from schemas.token import TokenInfo

from .yandex.schemas import YandexIdUserRequestParams


class OAuthLoginRequestParams(BaseModel):
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


class OAuthTokenRequestData(BaseModel):
    grant_type: str = "authorization_code"
    code: str
    device_id: UUID4 | None = None
    device_name: str | None = None
    code_verifier: str | None = None


class OAuthUserRequestParams(BaseModel):
    yandex: YandexIdUserRequestParams = Depends()


class OAuthLoginServiceOutput(BaseModel):
    tokens: TokenInfo | None = None
    user_email: EmailStr | None = None
