from dataclasses import dataclass
import os

DEFAULT_ROLE_TITLE = "user"
DEFAULT_ROLE_ACCESS_LABELS = ["free"]


@dataclass(frozen=True)
class FunctionalTestSettings:
    api_url: str = os.getenv("AUTH_TEST_API_URL", "http://localhost:8001")
    api_prefix: str = os.getenv("AUTH_TEST_API_PREFIX", "")
    request_timeout_seconds: float = float(os.getenv("AUTH_TEST_TIMEOUT", "10"))

    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5434"))
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "password")
    postgres_db: str = os.getenv("POSTGRES_DB", "auth")

    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", "6377"))

    superuser_email: str = os.getenv("SUPERUSER_EMAIL", "admin@example.com")
    superuser_password: str = os.getenv("SUPERUSER_PASSWORD", "password")

    yandex_mock_url: str = os.getenv("YANDEX_MOCK_URL", "http://localhost:8090")
    yandex_confirmation_code_ttl: int = int(os.getenv("YANDEX_CONFIRMATION_CODE_TTL", "600"))


test_settings = FunctionalTestSettings()
