from dataclasses import dataclass

import sentry_sdk
from sentry_sdk.transport import Transport
from starlette.exceptions import HTTPException

from app.core import sentry as sentry_setup


@dataclass
class Config:
    enabled: bool = True
    dsn: str | None = "http://public@example.com/1"
    environment: str = "test"
    release: str | None = "auth-api@test"


class RecordingTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def capture_event(self, event) -> None:
        self.events.append(event)

    def capture_envelope(self, envelope) -> None:
        self.events.extend(
            event
            for item in envelope.items
            if item.type == "event" and (event := item.get_event()) is not None
        )


def teardown_function() -> None:
    client = sentry_sdk.Hub.current.client
    if client is not None:
        client.close()
    sentry_sdk.Hub.current.bind_client(None)
    sentry_setup._configured = False


def test_legacy_store_transport_builds_store_url() -> None:
    transport = sentry_setup.LegacyStoreTransport("http://public@sentry-api:9000/3")
    assert transport._store_url == "http://sentry-api:9000/api/3/store/"
    assert transport._public_key == "public"


def test_configure_sentry_requires_enabled_dsn() -> None:
    assert not sentry_setup.configure_sentry(
        Config(enabled=False),
        service_name="auth-api",
    )
    assert not sentry_setup.configure_sentry(
        Config(dsn=None),
        service_name="auth-api",
    )
    assert not sentry_setup.configure_sentry(
        Config(dsn="   "),
        service_name="auth-api",
    )


def test_before_send_drops_http_errors_and_scrubs_sensitive_data() -> None:
    http_error = HTTPException(status_code=401)
    assert (
        sentry_setup._before_send(
            {},
            {"exc_info": (HTTPException, http_error, None)},
            service_name="auth-api",
        )
        is None
    )

    event = {
        "user": {"id": "private"},
        "request": {
            "cookies": {"session": "private"},
            "data": {"password": "private"},
            "headers": {
                "Authorization": "Bearer private",
                "Cookie": "session=private",
                "Accept": "application/json",
            },
        },
    }
    processed = sentry_setup._before_send(
        event,
        {},
        service_name="auth-api",
        request_id_getter=lambda: "request-123",
    )

    assert processed is not None
    assert "user" not in processed
    assert "cookies" not in processed["request"]
    assert "data" not in processed["request"]
    assert processed["request"]["headers"] == {"Accept": "application/json"}
    assert processed["tags"] == {
        "service": "auth-api",
        "request_id": "request-123",
    }


def test_unhandled_exception_reaches_transport() -> None:
    transport = RecordingTransport()
    assert sentry_setup.configure_sentry(
        Config(),
        service_name="auth-api",
        request_id_getter=lambda: "request-123",
        transport=transport,
    )

    sentry_sdk.capture_exception(HTTPException(status_code=404))
    sentry_sdk.capture_exception(RuntimeError("boom"))
    sentry_sdk.flush()

    assert len(transport.events) == 1
    assert transport.events[0]["tags"] == {
        "service": "auth-api",
        "request_id": "request-123",
    }
