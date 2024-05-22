from typing import Any

from flask.app import Flask
from opentelemetry.instrumentation.flask import FlaskInstrumentor


def instrument_flask(app: Flask, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
    FlaskInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
