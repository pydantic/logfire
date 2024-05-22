from typing import Any

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor


def instrument_httpx(**kwargs: Any):
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
    HTTPXClientInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
