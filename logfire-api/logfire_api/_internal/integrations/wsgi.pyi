from logfire import Logfire as Logfire
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from opentelemetry.trace import Span
from typing import Callable, Protocol, TypedDict
from typing_extensions import Unpack
from wsgiref.types import WSGIApplication, WSGIEnvironment

class ResponseHook(Protocol):
    def __call__(self, span: Span, environ: WSGIEnvironment, status_code: int, response_headers: list[tuple[str, str]]) -> None: ...
RequestHook = Callable[[Span, WSGIEnvironment], None]

class WSGIInstrumentKwargs(TypedDict, total=False):
    request_hook: RequestHook | None
    response_hook: ResponseHook | None

def instrument_wsgi(logfire_instance: Logfire, app: WSGIApplication, *, capture_headers: bool = False, **kwargs: Unpack[WSGIInstrumentKwargs]) -> WSGIApplication:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_wsgi` method for details.
    """
