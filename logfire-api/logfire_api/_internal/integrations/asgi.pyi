from collections.abc import Awaitable
from dataclasses import dataclass
from logfire import Logfire as Logfire
from logfire._internal.utils import is_asgi_send_receive_span_name as is_asgi_send_receive_span_name, maybe_capture_server_headers as maybe_capture_server_headers
from opentelemetry.context import Context
from opentelemetry.trace import Span, Tracer, TracerProvider
from typing import Any, Callable, Protocol, TypedDict
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

def tweak_asgi_spans_tracer_provider(logfire_instance: Logfire, record_send_receive: bool) -> TracerProvider:
    """If record_send_receive is False, return a TracerProvider that skips spans for ASGI send and receive events."""

@dataclass
class TweakAsgiTracerProvider(TracerProvider):
    tracer_provider: TracerProvider
    def get_tracer(self, *args: Any, **kwargs: Any) -> Tracer: ...

@dataclass
class TweakAsgiSpansTracer(Tracer):
    tracer: Tracer
    def start_span(self, name: str, context: Context | None = None, *args: Any, **kwargs: Any) -> Span: ...
    start_as_current_span = ...

def instrument_asgi(logfire_instance: Logfire, app: ASGIApp, *, record_send_receive: bool = False, capture_headers: bool = False, **kwargs: Unpack[ASGIInstrumentKwargs]) -> ASGIApp:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_asgi` method for details.
    """
