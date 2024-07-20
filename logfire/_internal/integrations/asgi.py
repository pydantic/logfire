from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

if TYPE_CHECKING:
    from typing import Any, Awaitable, Callable, Protocol, TypedDict

    from opentelemetry.trace import Span
    from typing_extensions import Unpack

    Scope = dict[str, Any]
    Receive = Callable[[], Awaitable[dict[str, Any]]]
    Send = Callable[[dict[str, Any]], Awaitable[None]]

    class ASGIApp(Protocol):
        def __call__(self, scope: Scope, receive: Receive, send: Send) -> Awaitable[None]: ...

    Hook = Callable[[Span, dict[str, Any]], None]

    class ASGIInstrumentKwargs(TypedDict, total=False):
        excluded_urls: str | None
        default_span_details: Callable[[Scope], tuple[str, dict[str, Any]]]
        server_request_hook: Hook | None
        client_request_hook: Hook | None
        client_response_hook: Hook | None
        http_capture_headers_server_request: list[str] | None
        http_capture_headers_server_response: list[str] | None
        http_capture_headers_sanitize_fields: list[str] | None


def instrument_asgi(app: ASGIApp, **kwargs: Unpack[ASGIInstrumentKwargs]) -> ASGIApp:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_asgi` method for details.
    """
    return OpenTelemetryMiddleware(app, **kwargs)
