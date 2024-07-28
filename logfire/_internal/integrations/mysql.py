from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.mysql import MySQLInstrumentor

if TYPE_CHECKING:
    from typing_extensions import TypedDict, Unpack

    class MySQLInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_mysql(**kwargs: Unpack[MySQLInstrumentKwargs]) -> None:
    """Instrument the `mysql` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_mysql` method for details.
    """
    MySQLInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
