from __future__ import annotations

from typing import Any, Callable

from django.http import HttpRequest, HttpResponse
from opentelemetry.trace import Span, get_current_span

from logfire._internal.utils import maybe_capture_server_headers

try:
    from opentelemetry.instrumentation.django import DjangoInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_django()` requires the `opentelemetry-instrumentation-django` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[django]'"
    )

_LOGFIRE_INSTRUMENTED = '_logfire_instrumented'


def instrument_django(
    *,
    capture_headers: bool,
    is_sql_commentor_enabled: bool | None,
    excluded_urls: str | None,
    request_hook: Callable[[Span, HttpRequest], None] | None,
    response_hook: Callable[[Span, HttpRequest, HttpResponse], None] | None,
    instrument_ninja: bool,
    **kwargs: Any,
) -> None:
    """Instrument the `django` module so that spans are automatically created for each web request.

    See the `Logfire.instrument_django` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    DjangoInstrumentor().instrument(
        excluded_urls=excluded_urls,
        is_sql_commentor_enabled=is_sql_commentor_enabled,
        request_hook=request_hook,
        response_hook=response_hook,
        **kwargs,
    )
    if instrument_ninja:
        _instrument_django_ninja()


def _instrument_django_ninja() -> None:
    """Patch NinjaAPI.on_exception at the class level to record exceptions on spans.

    Django Ninja catches exceptions before they propagate to Django's middleware,
    which prevents OpenTelemetry's Django instrumentation from recording them.
    """
    try:
        from ninja import NinjaAPI
    except ImportError:
        return

    if getattr(NinjaAPI.on_exception, _LOGFIRE_INSTRUMENTED, False):
        return

    original_on_exception = NinjaAPI.on_exception

    def patched_on_exception(self: Any, request: HttpRequest, exc: Exception) -> HttpResponse:
        span = get_current_span()
        try:
            response = original_on_exception(self, request, exc)
        except Exception:
            if span.is_recording():
                span.record_exception(exc, escaped=True)
            raise
        if span.is_recording():
            span.record_exception(exc, escaped=False)
        return response

    patched_on_exception._logfire_instrumented = True  # type: ignore[attr-defined]
    NinjaAPI.on_exception = patched_on_exception  # type: ignore[assignment]
