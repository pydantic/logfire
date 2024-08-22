from logfire import Logfire as Logfire
from logfire._internal.integrations.asgi import tweak_asgi_spans_tracer_provider as tweak_asgi_spans_tracer_provider
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from opentelemetry.instrumentation.asgi.types import ClientRequestHook, ClientResponseHook, ServerRequestHook
from starlette.applications import Starlette
from typing_extensions import TypedDict, Unpack

class StarletteInstrumentKwargs(TypedDict, total=False):
    server_request_hook: ServerRequestHook | None
    client_request_hook: ClientRequestHook | None
    client_response_hook: ClientResponseHook | None

def instrument_starlette(logfire_instance: Logfire, app: Starlette, *, record_send_receive: bool = False, capture_headers: bool = False, **kwargs: Unpack[StarletteInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
