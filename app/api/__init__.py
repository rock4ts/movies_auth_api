from .routes_auth import router as router_auth
from .routes_role import router as router_role
from .routes_user import router as router_user
from .routes_yandexid import router as router_yandexid

__all__ = (
    "router_auth",
    "router_user",
    "router_role",
    "router_yandexid",
)
