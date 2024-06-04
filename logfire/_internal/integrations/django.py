from typing import Any

try:
    from opentelemetry.instrumentation.django import DjangoInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_django()` requires the `opentelemetry-instrumentation-django` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[django]'"
    )


def instrument_django(**kwargs: Any):
    """Instrument the `django` module so that spans are automatically created for each web request.

    See the `Logfire.instrument_django` method for details.
    """
    DjangoInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
