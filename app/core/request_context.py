from contextvars import ContextVar, Token

from fastapi import Request
from app.core.config import settings


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    return _request_id.get() or "-"


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_client_ip(request: Request) -> str:
    direct_client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for or not settings.trust_proxy_headers:
        return direct_client_ip

    trusted_proxy_ips = settings.trusted_proxy_ip_set
    if trusted_proxy_ips and direct_client_ip not in trusted_proxy_ips:
        return direct_client_ip

    first_hop = forwarded_for.split(",")[0].strip()
    return first_hop or direct_client_ip
