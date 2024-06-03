from typing import Any

from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette


def instrument_starlette(app: Starlette, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
    StarletteInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
