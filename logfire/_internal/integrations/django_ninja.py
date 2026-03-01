from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse

try:
    from ninja import NinjaAPI
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_django_ninja()` requires the `django-ninja` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[django-ninja]'"
    )


_LOGFIRE_INSTRUMENTED = '_logfire_instrumented'


def instrument_django_ninja(
    api: NinjaAPI,
    **kwargs: Any,
) -> None:
    """Instrument a Django Ninja API so that exceptions are recorded on OpenTelemetry spans.

    Django Ninja catches exceptions before they propagate to Django's middleware,
    which prevents OpenTelemetry's Django instrumentation from recording them.
    This function patches the API's `on_exception` method to record exceptions
    on the current span before Django Ninja handles them.

    See the `Logfire.instrument_django_ninja` method for details.
    """
    if getattr(api.on_exception, _LOGFIRE_INSTRUMENTED, False):
        return

    from opentelemetry.trace import get_current_span

    original_on_exception = api.on_exception

    def patched_on_exception(request: HttpRequest, exc: Exception) -> HttpResponse:
        span = get_current_span()
        try:
            response = original_on_exception(request, exc)
        except Exception:
            if span.is_recording():  # pragma: no branch
                span.record_exception(exc, escaped=True)
            raise
        if span.is_recording():  # pragma: no branch
            span.record_exception(exc, escaped=False)
        return response

    patched_on_exception._logfire_instrumented = True  # type: ignore[attr-defined]
    api.on_exception = patched_on_exception  # type: ignore[method-assign]
