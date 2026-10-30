from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from opentelemetry.sdk.trace import Span
from opentelemetry.util.http import SanitizeValue, redact_url

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
    # OTel's redact_url handles legacy S3, Azure SAS, and Google signed URLs.
    # Reuse its sanitizer for SigV4 fields not yet covered by redact_url.
    sanitize = SanitizeValue([r'^X-Amz-(Signature|Credential|Security-Token)$'])

    def filter_url(url: str) -> str:
        url = redact_url(url_filter(url) if url_filter is not None else url)
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        sanitized = [(key, sanitize.sanitize_header_value(key, value)) for key, value in query]
        if sanitized != query:
            return urlunsplit(parts._replace(query=urlencode(sanitized)))
        return url

    URLLib3Instrumentor().instrument(
        excluded_urls=excluded_urls,
        request_hook=request_hook,
        response_hook=response_hook,
        url_filter=filter_url,
        **kwargs,
    )
