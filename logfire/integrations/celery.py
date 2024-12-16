from typing import TypedDict


class CeleryInstrumentKwargs(TypedDict, total=False):
    """Keyword arguments for the [`logfire.instrument_celery`][logfire.Logfire.instrument_celery] function."""

    skip_dep_check: bool
    """Whether to skip the dependency check for the `celery` module.

    This is used to determine if the `celery` module is available.
    """
