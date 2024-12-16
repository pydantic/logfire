from typing import TypedDict

class CeleryInstrumentKwargs(TypedDict, total=False):
    """Keyword arguments for the [`logfire.instrument_celery`][logfire.Logfire.instrument_celery] function."""
    skip_dep_check: bool
