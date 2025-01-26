import os

from async_fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv
from pydantic import HttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_prefix="TESTS_CONFIG__")

    # Если в окружении уже есть переменные, нужно их переписать
    def __init__(self, **data):
        env_file_path = data.pop("env_file_path", ".env.tests-local")

        if os.path.exists(env_file_path):
            load_dotenv(env_file_path, override=True)

        super().__init__(**data)


class DbSettings(BaseSettings):
    pg_url: PostgresDsn
    pg_url_sync: PostgresDsn


class RedisSettings(BaseSettings):
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379


class WebAppSettings(BaseSettings):
    service_host: str = "127.0.0.1"
    service_port: int = 8000

    authjwt_secret_key: str = "secret"
    authjwt_algorithm: str = "HS256"

    oauth_yandex_email: str = "rock4ts@yandex.ru"
    oauth_yandex_mock_token_endpoint: str = "/mock/yandex-token"
    oauth_yandex_mock_user_endpoint: str = "/mock/yandex-user"
    oauth_yandex_mock_code: str = "123qwerty"

    @property
    def service_url(self) -> HttpUrl:
        return f"http://{self.service_host}:{self.service_port}/auth"



pg_settings = DbSettings(env_file_path=".env.tests-local")
redis_settings = RedisSettings(env_file_path=".env.tests-local")
webapp_settings = WebAppSettings(env_file_path=".env.tests-local")


@AuthJWT.load_config
def get_config():
    return webapp_settings
