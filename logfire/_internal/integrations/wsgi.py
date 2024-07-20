from __future__ import annotations

from typing import TYPE_CHECKING
from wsgiref.types import WSGIApplication, WSGIEnvironment

from opentelemetry.instrumentation.wsgi import OpenTelemetryMiddleware

if TYPE_CHECKING:
    from typing import Callable, Protocol, TypedDict

    from opentelemetry.trace import Span
    from typing_extensions import Unpack

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


def instrument_wsgi(app: WSGIApplication, **kwargs: Unpack[WSGIInstrumentKwargs]) -> WSGIApplication:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_wsgi` method for details.
    """
    return OpenTelemetryMiddleware(app, **kwargs)
