from logging import config as logging_config
from pathlib import Path

from async_fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel, PostgresDsn
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
    url: str = "localhost"
    port: int = 6379


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
    redis: RedisConfig = RedisConfig()


settings = Settings()


@AuthJWT.load_config
def get_config():
    return settings
