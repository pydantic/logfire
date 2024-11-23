from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_celery()` requires the `opentelemetry-instrumentation-celery` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[celery]'"
    )

from logfire import Logfire

if TYPE_CHECKING:
    from typing_extensions import TypedDict, Unpack

    class CeleryInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_celery(logfire_instance: Logfire, **kwargs: Unpack[CeleryInstrumentKwargs]) -> None:
    """Instrument the `celery` module so that spans are automatically created for each task.

    See the `Logfire.instrument_celery` method for details.
    """
    return CeleryInstrumentor().instrument(  # type: ignore[reportUnknownMemberType]
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        }
    )
