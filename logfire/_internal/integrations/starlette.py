from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette

from logfire import Logfire
from logfire._internal.integrations.asgi import tweak_asgi_spans_tracer_provider
from logfire._internal.utils import maybe_capture_server_headers

if TYPE_CHECKING:
    from opentelemetry.instrumentation.asgi.types import ClientRequestHook, ClientResponseHook, ServerRequestHook
    from typing_extensions import TypedDict, Unpack

    class StarletteInstrumentKwargs(TypedDict, total=False):
        server_request_hook: ServerRequestHook | None
        client_request_hook: ClientRequestHook | None
        client_response_hook: ClientResponseHook | None


def instrument_starlette(
    logfire_instance: Logfire,
    app: Starlette,
    *,
    record_send_receive: bool = False,
    capture_headers: bool = False,
    **kwargs: Unpack[StarletteInstrumentKwargs],
):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    StarletteInstrumentor().instrument_app(  # type: ignore[reportUnknownMemberType]
        app,
        tracer_provider=tweak_asgi_spans_tracer_provider(logfire_instance, record_send_receive),
        **kwargs,
    )
