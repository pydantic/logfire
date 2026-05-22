import requests
from collections.abc import Callable
from opentelemetry.sdk.trace import Span as Span
from typing import Any

def instrument_requests(excluded_urls: str | None = None, request_hook: Callable[[Span, requests.PreparedRequest], None] | None = None, response_hook: Callable[[Span, requests.PreparedRequest, requests.Response], None] | None = None, **kwargs: Any) -> None:
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
