from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_asyncpg()` requires the `opentelemetry-instrumentation-asyncpg` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[asyncpg]'"
    )

from logfire import Logfire

if TYPE_CHECKING:
    from typing_extensions import TypedDict, Unpack

    class AsyncPGInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_asyncpg(logfire_instance: Logfire, **kwargs: Unpack[AsyncPGInstrumentKwargs]) -> None:
    """Instrument the `asyncpg` module so that spans are automatically created for each query.

    See the `Logfire.instrument_asyncpg` method for details.
    """
    AsyncPGInstrumentor().instrument(  # type: ignore[reportUnknownMemberType]
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        }
    )
