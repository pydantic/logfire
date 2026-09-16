from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from opentelemetry.sdk.trace import Span

if TYPE_CHECKING:
    from opentelemetry.instrumentation.urllib3 import RequestInfo
    from urllib3.connectionpool import HTTPConnectionPool
    from urllib3.response import HTTPResponse

try:
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
except ImportError as _err:
    raise RuntimeError(
        '`logfire.instrument_urllib3()` requires the `opentelemetry-instrumentation-urllib3` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[urllib3]'"
    ) from _err


def instrument_urllib3(
    excluded_urls: str | None = None,
    request_hook: Callable[[Span, HTTPConnectionPool, RequestInfo], None] | None = None,
    response_hook: Callable[[Span, HTTPConnectionPool, HTTPResponse], None] | None = None,
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
