from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

try:
    from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_sqlite3()` requires the `opentelemetry-instrumentation-sqlite3` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[sqlite3]'"
    )

if TYPE_CHECKING:
    from typing import TypedDict, TypeVar, Unpack

    from opentelemetry.trace import TracerProvider

    SQLite3Connection = TypeVar('SQLite3Connection', bound=sqlite3.Connection | None)

    class SQLite3InstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_sqlite3(
    *, conn: SQLite3Connection, tracer_provider: TracerProvider, **kwargs: Unpack[SQLite3InstrumentKwargs]
) -> SQLite3Connection:
    """Instrument the `sqlite3` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlite3` method for details.
    """
    if conn is not None:
        return SQLite3Instrumentor().instrument_connection(conn, tracer_provider=tracer_provider)  # type: ignore[reportUnknownMemberType]
    else:
        return SQLite3Instrumentor().instrument(tracer_provider=tracer_provider, **kwargs)  # type: ignore[reportUnknownMemberType]
