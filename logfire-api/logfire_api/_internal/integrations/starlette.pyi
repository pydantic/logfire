from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from opentelemetry.trace import Span
from starlette.applications import Starlette
from typing import Any
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

def instrument_starlette(app: Starlette, *, capture_headers: bool = False, **kwargs: Unpack[StarletteInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
