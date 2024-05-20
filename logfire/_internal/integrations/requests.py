from typing import Any, Optional

from opentelemetry.instrumentation.requests import RequestsInstrumentor


def instrument_requests(excluded_urls: Optional[str] = None, **kwargs: Any):
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
    RequestsInstrumentor().instrument(excluded_urls=excluded_urls, **kwargs)  # type: ignore[reportUnknownMemberType]
