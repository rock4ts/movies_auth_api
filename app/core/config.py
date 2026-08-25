# from async_fastapi_jwt_auth import AuthJWT
import base64
from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings

from app.core.enums import AccessLabel

DEFAULT_ROLE_TITLE = "user"
DEFAULT_ROLE_ACCESS_LABELS: tuple[AccessLabel, ...] = (AccessLabel.FREE,)


class PostgresSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5433, validation_alias="POSTGRES_PORT")
    user: str = Field(default="postgres", validation_alias="POSTGRES_USER")
    password: str = Field(default="password", validation_alias="POSTGRES_PASSWORD")
    db: str = Field(default="auth", validation_alias="POSTGRES_DB")

    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class RedisSettings(BaseSettings):
    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")


class YandexIdSettings(BaseSettings):
    auth_url: str = Field(
        default="https://oauth.yandex.ru/authorize", validation_alias="YANDEXID_AUTH_URL"
    )
    token_url: str = Field(
        default="https://oauth.yandex.ru/token", validation_alias="YANDEXID_TOKEN_URL"
    )
    user_info_url: str = Field(
        default="https://login.yandex.ru/info", validation_alias="YANDEXID_USER_INFO_URL"
    )
    redirect_url: str = Field(
        default="http://localhost:8000/yandexid/token",
        validation_alias="YANDEXID_REDIRECT_URL",
    )
    client_id: str = Field(validation_alias="YANDEXID_CLIENT_ID")
    client_secret: str = Field(validation_alias="YANDEXID_CLIENT_SECRET")
    confirmation_code_ttl: int = Field(
        default=600,
        validation_alias="YANDEX_CONFIRMATION_CODE_TTL",
    )
    http_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="YANDEXID_HTTP_TIMEOUT_SECONDS",
    )

    @cached_property
    def auth_header(self) -> str:
        encoded_client_data = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()  # noqa: E501
        return f"Basic {encoded_client_data}"


class JWTSettings(BaseSettings):
    algorithm: str = "RS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    private_key_path: str = "certs/jwt-private.pem"
    public_key_path: str = "certs/jwt-public.pem"

    @cached_property
    def private_key(self) -> bytes:
        with open(self.private_key_path, "rb") as key_file:
            return key_file.read()

    @cached_property
    def public_key(self) -> bytes:
        with open(self.public_key_path, "rb") as key_file:
            return key_file.read()


class TracingSettings(BaseSettings):
    enabled: bool = Field(default=False, validation_alias="TRACING_ENABLED")
    service_name: str = Field(default="auth-api", validation_alias="OTEL_SERVICE_NAME")
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT",
    )
    otlp_insecure: bool = Field(default=True, validation_alias="OTEL_EXPORTER_OTLP_INSECURE")
    traces_sampler: str = Field(
        default="parentbased_traceidratio",
        validation_alias="OTEL_TRACES_SAMPLER",
    )
    traces_sampler_arg: float = Field(default=1.0, validation_alias="OTEL_TRACES_SAMPLER_ARG")
    redis_capture_statement: bool = Field(
        default=False,
        validation_alias="OTEL_PYTHON_REDIS_CAPTURE_STATEMENT",
    )


class RateLimitSettings(BaseSettings):
    enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")
    redis_prefix: str = Field(default="rate_limit", validation_alias="RATE_LIMIT_REDIS_PREFIX")
    fail_open: bool = Field(default=False, validation_alias="RATE_LIMIT_FAIL_OPEN")
    ip_limit: int = Field(default=5, validation_alias="RATE_LIMIT_IP_LIMIT")
    ip_window_seconds: int = Field(default=60, validation_alias="RATE_LIMIT_IP_WINDOW_SECONDS")


class AppSettings(BaseSettings):
    debug: bool = False
    prod: bool = Field(default=False, validation_alias="PROD_RUN")
    reset_db_on_startup: bool = Field(default=False, validation_alias="RESET_DB_ON_STARTUP")
    log_file_path: str | None = Field(default=None, validation_alias="LOG_FILE_PATH")
    log_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        validation_alias="LOG_MAX_BYTES",
        ge=1,
    )
    log_backup_count: int = Field(default=7, validation_alias="LOG_BACKUP_COUNT", ge=0)
    superuser_email: str = Field(default="admin@example.com", validation_alias="SUPERUSER_EMAIL")
    superuser_password: str = Field(default="password", validation_alias="SUPERUSER_PASSWORD")
    request_id_header: str = Field(default="x-request-id", validation_alias="REQUEST_ID_HEADER")
    trust_proxy_headers: bool = Field(default=False, validation_alias="TRUST_PROXY_HEADERS")
    trusted_proxy_ips: str = Field(default="", validation_alias="TRUSTED_PROXY_IPS")
    # jaeger: JaegerConfig

    @property
    def trusted_proxy_ip_set(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}


settings = AppSettings()
db_settings = PostgresSettings()
redis_settings = RedisSettings()
jwt_settings = JWTSettings()
tracing_settings = TracingSettings()
rate_limit_settings = RateLimitSettings()
yandexid_settings = YandexIdSettings()
