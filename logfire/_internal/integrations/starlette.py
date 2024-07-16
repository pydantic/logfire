from typing import Any

from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette

from logfire._internal.utils import maybe_capture_server_headers


def instrument_starlette(app: Starlette, *, capture_headers: bool = False, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    StarletteInstrumentor().instrument_app(app, **kwargs)  # type: ignore[reportUnknownMemberType]
