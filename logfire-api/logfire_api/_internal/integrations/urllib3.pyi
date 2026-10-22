from collections.abc import Callable
from opentelemetry.instrumentation.urllib3 import RequestInfo as RequestInfo
from opentelemetry.sdk.trace import Span as Span
from typing import Any
from urllib3.connectionpool import HTTPConnectionPool as HTTPConnectionPool
from urllib3.response import HTTPResponse as HTTPResponse

def instrument_urllib3(excluded_urls: str | None = None, request_hook: Callable[[Span, HTTPConnectionPool, RequestInfo], None] | None = None, response_hook: Callable[[Span, HTTPConnectionPool, HTTPResponse], None] | None = None, url_filter: Callable[[str], str] | None = None, **kwargs: Any) -> None:
    """Instrument the `urllib3` module so that spans are automatically created for each request.

    See the `Logfire.instrument_urllib3` method for details.
    """
