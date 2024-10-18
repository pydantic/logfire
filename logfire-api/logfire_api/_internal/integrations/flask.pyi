from flask.app import Flask
from logfire import Logfire as Logfire
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from opentelemetry.trace import Span
from typing_extensions import Protocol, TypedDict, Unpack
from wsgiref.types import WSGIEnvironment

class RequestHook(Protocol):
    def __call__(self, span: Span, environment: WSGIEnvironment) -> None: ...

class ResponseHook(Protocol):
    def __call__(self, span: Span, status: str, response_headers: list[tuple[str, str]]) -> None: ...

class FlaskInstrumentKwargs(TypedDict, total=False):
    request_hook: RequestHook | None
    response_hook: RequestHook | None
    excluded_urls: str | None
    enable_commenter: bool | None
    commenter_options: dict[str, str] | None

def instrument_flask(logfire_instance: Logfire, app: Flask, capture_headers: bool = False, **kwargs: Unpack[FlaskInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
