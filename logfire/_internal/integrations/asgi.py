from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from opentelemetry.context import Context
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.sdk.trace import Tracer as SDKTracer
from opentelemetry.trace import NonRecordingSpan, Span, Tracer, TracerProvider
from opentelemetry.trace.propagation import get_current_span

from logfire._internal.utils import is_asgi_send_receive_span_name, maybe_capture_server_headers

if TYPE_CHECKING:
    from typing import Any, Awaitable, Callable, Protocol, TypedDict

    from opentelemetry.trace import Span
    from typing_extensions import Unpack

    from logfire import Logfire

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
    tracer_provider = logfire_instance.config.get_tracer_provider()
    if record_send_receive:
        return tracer_provider
    else:
        return TweakAsgiTracerProvider(tracer_provider)


@dataclass
class TweakAsgiTracerProvider(TracerProvider):
    tracer_provider: TracerProvider

    def get_tracer(self, *args: Any, **kwargs: Any) -> Tracer:
        return TweakAsgiSpansTracer(self.tracer_provider.get_tracer(*args, **kwargs))


@dataclass
class TweakAsgiSpansTracer(Tracer):
    tracer: Tracer

    def start_span(self, name: str, context: Context | None = None, *args: Any, **kwargs: Any) -> Span:
        if is_asgi_send_receive_span_name(name):
            # These are the noisy spans we want to skip.
            # Create a no-op span with the same SpanContext as the current span.
            # This means that any spans created within will have the current span as their parent,
            # as if this span didn't exist at all.
            return NonRecordingSpan(get_current_span(context).get_span_context())

        return self.tracer.start_span(name, context, *args, **kwargs)

    # This means that `with start_as_current_span(...):`
    # is roughly equivalent to `with use_span(start_span(...)):`
    start_as_current_span = SDKTracer.start_as_current_span


def instrument_asgi(
    logfire_instance: Logfire,
    app: ASGIApp,
    *,
    record_send_receive: bool = False,
    capture_headers: bool = False,
    **kwargs: Unpack[ASGIInstrumentKwargs],
) -> ASGIApp:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_asgi` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    return OpenTelemetryMiddleware(
        app,
        **{  # type: ignore
            'tracer_provider': tweak_asgi_spans_tracer_provider(logfire_instance, record_send_receive),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )
