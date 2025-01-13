import base64
from functools import cached_property
from logging import config as logging_config
from pathlib import Path

from async_fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel, HttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logger import LOGGING

BASE_DIR = Path(__file__).parent.parent

# Применяем настройки логирования
logging_config.dictConfig(LOGGING)


class RunConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class DatabaseConfig(BaseModel):
    url: PostgresDsn
    sync_url: PostgresDsn
    echo: bool = False
    echo_pool: bool = False
    pool_size: int = 50
    max_overflow: int = 10

    naming_conventions: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379


class JaegerConfig(BaseModel):
    host: str = 'localhost'
    port: int = 4317


class OAuthYandexConfig(BaseModel):
    auth_url: HttpUrl = "https://oauth.yandex.ru/authorize"
    token_url: HttpUrl = "https://oauth.yandex.ru/token"
    user_info_url: HttpUrl = "https://login.yandex.ru/info"
    redirect_url: HttpUrl = "https://oauth.yandex.ru/verification_code" # for tests
    client_id: str = None
    client_secret: str = None

    @cached_property
    def auth_header(self) -> str:
        client_data = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()  # noqa: E501
        return f"Basic {client_data}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        case_sensitive=False,
        env_nested_delimiter="__",
        env_prefix="APP_CONFIG__",
    )
    run: RunConfig = RunConfig()
    db: DatabaseConfig
    authjwt_secret_key: str
    authjwt_algorithm: str = "HS256"
    redis: RedisConfig
    jaeger: JaegerConfig
    oauth_yandex: OAuthYandexConfig


settings = Settings()


@AuthJWT.load_config
def get_config():
    return settings
