from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from opentelemetry.util.http import SanitizeValue, redact_url

from ..utils import get_version

_MINIMUM_VERSION = '0.61b0'
_INSTALL_INSTRUCTIONS = "\nYou can install a compatible version with:\n    pip install -U 'logfire[urllib3]'"


def instrument_urllib3(url_filter: Callable[[str], str] | None = None, **kwargs: Any) -> None:
    """Configure the upstream instrumentor with a URL filter that redacts signed credentials."""
    try:
        from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
        from opentelemetry.instrumentation.urllib3.version import __version__
    except ModuleNotFoundError as exc:
        if exc.name != 'opentelemetry.instrumentation.urllib3':
            raise
        raise RuntimeError(
            '`logfire.instrument_urllib3()` requires the `opentelemetry-instrumentation-urllib3` package.'
            + _INSTALL_INSTRUCTIONS
        ) from exc

    if get_version(__version__) < get_version(_MINIMUM_VERSION):
        raise RuntimeError(
            f'`logfire.instrument_urllib3()` requires `opentelemetry-instrumentation-urllib3 >= {_MINIMUM_VERSION}`.'
            + _INSTALL_INSTRUCTIONS
        )

    # OTel's redact_url handles legacy S3, Azure SAS, and Google signed URLs.
    # Reuse its sanitizer for SigV4 fields not yet covered by redact_url.
    sanitize = SanitizeValue([r'^X-Amz-(Signature|Credential|Security-Token)$'])

    def filter_url(url: str) -> str:
        url = url_filter(url) if url_filter is not None else url
        try:
            url = redact_url(url)
            parts = urlsplit(url)
        except ValueError:
            # An invalid telemetry URL should neither abort the request nor expose credentials.
            return '[REDACTED]'
        query = parse_qsl(parts.query, keep_blank_values=True)
        sanitized = [(key, sanitize.sanitize_header_value(key, value)) for key, value in query]
        if sanitized != query:
            return urlunsplit(parts._replace(query=urlencode(sanitized)))
        return url

    URLLib3Instrumentor().instrument(url_filter=filter_url, **kwargs)
