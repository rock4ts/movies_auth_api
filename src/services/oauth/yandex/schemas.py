from pydantic import BaseModel, EmailStr


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
