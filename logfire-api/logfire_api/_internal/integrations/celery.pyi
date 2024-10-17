from logfire import Logfire as Logfire
from typing_extensions import TypedDict, Unpack

class CeleryInstrumentKwargs(TypedDict, total=False):
    skip_dep_check: bool

def instrument_celery(logfire_instance: Logfire, **kwargs: Unpack[CeleryInstrumentKwargs]) -> None:
    """Instrument the `celery` module so that spans are automatically created for each task.

    See the `Logfire.instrument_celery` method for details.
    """
