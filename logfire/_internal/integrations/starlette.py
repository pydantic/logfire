from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette

if TYPE_CHECKING:
    from opentelemetry.metrics import MeterProvider
    from opentelemetry.trace import Span, TracerProvider
    from typing_extensions import Protocol, TypedDict, Unpack

    class ServerRequestHook(Protocol):
        def __call__(self, span: Span, scope: dict[str, Any]): ...

    class ClientRequestHook(Protocol):
        def __call__(self, span: Span, scope: dict[str, Any]): ...

    class ClientResponseHook(Protocol):
        def __call__(self, span: Span, message: dict[str, Any]): ...

    class StarletteInstrumentKwargs(TypedDict, total=False):
        server_request_hook: ServerRequestHook | None
        client_request_hook: ClientRequestHook | None
        client_response_hook: ClientResponseHook | None
        tracer_provider: TracerProvider | None
        meter_provider: MeterProvider | None


def instrument_starlette(app: Starlette, **kwargs: Unpack[StarletteInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
    StarletteInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
