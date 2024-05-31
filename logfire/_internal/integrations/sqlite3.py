from __future__ import annotations

from typing import Any

try:
    from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        'The `logfire.instrument_sqlite3()` requires the `opentelemetry-instrumentation-sqlite3` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[sqlite3]'"
    )


def instrument_sqlite3(**kwargs: Any):
    """Instrument the `sqlite3` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlite3` method for details.
    """
    SQLite3Instrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
