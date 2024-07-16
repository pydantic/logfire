from typing import Any

from flask.app import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor

from logfire._internal.utils import maybe_capture_server_headers


def instrument_flask(app: Flask, capture_headers: bool = False, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    FlaskInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
