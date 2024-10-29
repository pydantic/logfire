from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

from logfire._internal.utils import maybe_capture_server_headers

if TYPE_CHECKING:
    from typing import Callable, Protocol, TypedDict
    from wsgiref.types import WSGIApplication, WSGIEnvironment

    from opentelemetry.trace import Span
    from typing_extensions import Unpack

    from logfire import Logfire

    class ResponseHook(Protocol):
        def __call__(
            self, span: Span, environ: WSGIEnvironment, status_code: int, response_headers: list[tuple[str, str]]
        ) -> None: ...

    RequestHook = Callable[[Span, WSGIEnvironment], None]

    class WSGIInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook | None
        """A callback called when a request is received by the server."""
        response_hook: ResponseHook | None
        """A callback called when a response is sent by the server."""


def instrument_wsgi(
    logfire_instance: Logfire,
    app: WSGIApplication,
    *,
    capture_headers: bool = False,
    **kwargs: Unpack[WSGIInstrumentKwargs],
) -> WSGIApplication:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_wsgi` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    return OpenTelemetryMiddleware(
        app,
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )
