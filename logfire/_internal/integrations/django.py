from typing import Any

from logfire._internal.utils import maybe_capture_server_headers

try:
    from opentelemetry.instrumentation.django import DjangoInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_django()` requires the `opentelemetry-instrumentation-django` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[django]'"
    )


def instrument_django(*, capture_headers: bool = False, **kwargs: Any):
    """Instrument the `django` module so that spans are automatically created for each web request.

    See the `Logfire.instrument_django` method for details.
    """
    maybe_capture_server_headers(capture_headers)
    DjangoInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
