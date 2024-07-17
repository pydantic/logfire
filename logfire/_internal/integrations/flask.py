from __future__ import annotations

from typing import TYPE_CHECKING

from flask.app import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor

if TYPE_CHECKING:
    from wsgiref.types import WSGIEnvironment

    from opentelemetry.metrics import MeterProvider
    from opentelemetry.trace import Span, TracerProvider
    from typing_extensions import Protocol, TypedDict, Unpack

    class RequestHook(Protocol):
        def __call__(self, span: Span, environment: WSGIEnvironment) -> None: ...

    class ResponseHook(Protocol):
        def __call__(self, span: Span, status: str, response_headers: list[tuple[str, str]]) -> None: ...

    class FlaskInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook | None
        response_hook: RequestHook | None
        tracer_provider: TracerProvider | None
        excluded_urls: str | None
        enable_commenter: bool | None
        commenter_options: dict[str, str] | None
        meter_provider: MeterProvider | None


def instrument_flask(app: Flask, **kwargs: Unpack[FlaskInstrumentKwargs]):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
    FlaskInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
