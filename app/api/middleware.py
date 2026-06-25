from uuid import uuid4

from opentelemetry import trace
from opentelemetry.trace import Span
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import reset_request_id, set_request_id


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "x-request-id") -> None:
        self.app = app
        self.header_name = header_name.lower()
        self.header_bytes = self.header_name.encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._get_request_id(scope) or str(uuid4())
        token = set_request_id(request_id)
        self._set_span_request_id(trace.get_current_span(), request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [
                    (name, value) for name, value in headers if name.lower() != self.header_bytes
                ]
                headers.append((self.header_bytes, request_id.encode("latin-1")))
                message["headers"] = headers

            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)

    def _get_request_id(self, scope: Scope) -> str | None:
        for name, value in scope.get("headers", []):
            if name.lower() == self.header_bytes:
                request_id = value.decode("latin-1").strip()
                return request_id or None
        return None

    @staticmethod
    def _set_span_request_id(span: Span, request_id: str) -> None:
        if span.is_recording():
            span.set_attribute("http.request_id", request_id)
