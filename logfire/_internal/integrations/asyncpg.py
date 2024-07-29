from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

if TYPE_CHECKING:
    from typing_extensions import TypedDict, Unpack

    class AsyncPGInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_asyncpg(**kwargs: Unpack[AsyncPGInstrumentKwargs]) -> None:
    """Instrument the `asyncpg` module so that spans are automatically created for each query.

    See the `Logfire.instrument_asyncpg` method for details.
    """
    AsyncPGInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
