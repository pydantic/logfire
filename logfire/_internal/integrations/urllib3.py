from __future__ import annotations

from typing import Any, Callable

import urllib3.connectionpool
import urllib3.response
from opentelemetry.sdk.trace import Span

try:
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_urllib3()` requires the `opentelemetry-instrumentation-urllib3` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[urllib3]'"
    )


def instrument_urllib3(
    excluded_urls: str | None = None,
    request_hook: Callable[[Span, urllib3.connectionpool.HTTPConnectionPool, Any], None] | None = None,
    response_hook: Callable[[Span, urllib3.connectionpool.HTTPConnectionPool, urllib3.response.HTTPResponse], None]
    | None = None,
    url_filter: Callable[[str], str] | None = None,
    **kwargs: Any,
) -> None:
    """Instrument the `urllib3` module so that spans are automatically created for each request.

    See the `Logfire.instrument_urllib3` method for details.
    """
    URLLib3Instrumentor().instrument(
        excluded_urls=excluded_urls,
        request_hook=request_hook,
        response_hook=response_hook,
        url_filter=url_filter,
        **kwargs,
    )
