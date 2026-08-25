import json
import logging
from collections.abc import Callable
from functools import partial
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport
from starlette.exceptions import HTTPException

_SENSITIVE_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "set-cookie"})
_configured = False
logger = logging.getLogger(__name__)


class SentryConfig(Protocol):
    enabled: bool
    dsn: str | None
    environment: str
    release: str | None


class LegacyStoreTransport(Transport):
    """Send error events to the on-premise Sentry 9 `/store/` endpoint."""

    def __init__(self, dsn: str) -> None:
        super().__init__()
        parsed = urlparse(dsn)
        project_id = parsed.path.strip("/")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._store_url = f"{parsed.scheme}://{parsed.hostname}:{port}/api/{project_id}/store/"
        self._public_key = parsed.username or ""

    def capture_event(self, event) -> None:
        self._post_event(event)

    def capture_envelope(self, envelope) -> None:
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self._post_event(event)

    def _post_event(self, event: dict[str, Any]) -> None:
        body = json.dumps(event).encode()
        request = Request(
            self._store_url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Sentry-Auth": (
                    f"Sentry sentry_version=7, sentry_client=sentry.python/1.45.0, "
                    f"sentry_key={self._public_key}"
                ),
            },
        )
        try:
            with urlopen(request, timeout=5) as response:
                response.read()
        except HTTPError as exc:
            logger.warning(
                "Failed to send Sentry event to %s: %s %s",
                self._store_url,
                exc.code,
                exc.read().decode(errors="replace"),
            )
        except Exception:
            logger.warning("Failed to send Sentry event to %s", self._store_url, exc_info=True)


def _scrub_sensitive_data(event: dict[str, Any]) -> None:
    event.pop("user", None)
    request = event.get("request")
    if not isinstance(request, dict):
        return

    request.pop("cookies", None)
    request.pop("data", None)
    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in tuple(headers):
            if name.lower() in _SENSITIVE_HEADERS:
                headers.pop(name, None)
    elif isinstance(headers, list):
        request["headers"] = [
            header
            for header in headers
            if not (
                isinstance(header, (list, tuple))
                and header
                and str(header[0]).lower() in _SENSITIVE_HEADERS
            )
        ]


def _before_send(
    event: dict[str, Any],
    hint: dict[str, Any],
    *,
    service_name: str,
    request_id_getter: Callable[[], str] | None = None,
) -> dict[str, Any] | None:
    exc_info = hint.get("exc_info")
    if isinstance(exc_info, tuple) and len(exc_info) > 1 and isinstance(exc_info[1], HTTPException):
        return None

    _scrub_sensitive_data(event)
    tags = event.setdefault("tags", {})
    if isinstance(tags, dict):
        tags["service"] = service_name
        if request_id_getter is not None:
            request_id = request_id_getter()
            if request_id and request_id != "-":
                tags["request_id"] = request_id
    return event


def configure_sentry(
    config: SentryConfig,
    *,
    service_name: str,
    request_id_getter: Callable[[], str] | None = None,
    transport: Any = None,
) -> bool:
    global _configured

    dsn = (config.dsn or "").strip()
    if _configured or not config.enabled or not dsn:
        return False

    options: dict[str, Any] = {
        "dsn": dsn,
        "environment": config.environment,
        "release": config.release,
        "send_default_pii": False,
        "send_client_reports": False,
        "request_bodies": "never",
        "traces_sample_rate": 0.0,
        "profiles_sample_rate": 0.0,
        "integrations": [
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        "before_send": partial(
            _before_send,
            service_name=service_name,
            request_id_getter=request_id_getter,
        ),
        "transport": transport if transport is not None else LegacyStoreTransport(dsn),
    }

    sentry_sdk.init(**options)
    _configured = True
    return True
