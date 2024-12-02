import sqlite3
from opentelemetry.trace import TracerProvider
from typing import TypeVar, TypedDict, Unpack

SQLite3Connection = TypeVar('SQLite3Connection', bound=sqlite3.Connection | None)

class SQLite3InstrumentKwargs(TypedDict, total=False):
    skip_dep_check: bool

def instrument_sqlite3(*, conn: SQLite3Connection, tracer_provider: TracerProvider, **kwargs: Unpack[SQLite3InstrumentKwargs]) -> SQLite3Connection:
    """Instrument the `sqlite3` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlite3` method for details.
    """
