from __future__ import annotations

from typing import TYPE_CHECKING

from flask.app import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from logfire._internal.utils import maybe_capture_server_headers

if TYPE_CHECKING:
    from wsgiref.types import WSGIEnvironment

    from opentelemetry.trace import Span
    from typing_extensions import Protocol, TypedDict, Unpack

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


def instrument_flask(app: Flask, capture_headers: bool = False, **kwargs: Unpack[FlaskInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    FlaskInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
