from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.celery import CeleryInstrumentor

if TYPE_CHECKING:
    from opentelemetry.metrics import MeterProvider
    from opentelemetry.trace import TracerProvider
    from typing_extensions import TypedDict, Unpack

    class CeleryInstrumentKwargs(TypedDict, total=False):
        tracer_provider: TracerProvider | None
        meter_provider: MeterProvider | None
        skip_dep_check: bool


def instrument_celery(**kwargs: Unpack[CeleryInstrumentKwargs]) -> None:
    """Instrument the `celery` module so that spans are automatically created for each task.

    See the `Logfire.instrument_celery` method for details.
    """
    return CeleryInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
