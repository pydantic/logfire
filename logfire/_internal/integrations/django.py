from typing import Any

from opentelemetry.instrumentation.django import DjangoInstrumentor


def instrument_django(**kwargs: Any):
    """Instrument the `django` module so that spans are automatically created for each web request.

    See the `Logfire.instrument_django` method for details.
    """
    DjangoInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
