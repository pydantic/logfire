from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.trace import TracerProvider

try:
    from opentelemetry.instrumentation.mysql import MySQLInstrumentor
except ModuleNotFoundError:
    raise RuntimeError(
        '`logfire.instrument_mysql()` requires the `opentelemetry-instrumentation-mysql` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[mysql]'"
    )

if TYPE_CHECKING:
    from mysql.connector.abstracts import MySQLConnectionAbstract
    from mysql.connector.pooling import PooledMySQLConnection
    from typing_extensions import TypedDict, TypeVar, Unpack

    MySQLConnection = TypeVar('MySQLConnection', bound=PooledMySQLConnection | MySQLConnectionAbstract | None)

    class MySQLInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_mysql(
    *,
    conn: MySQLConnection = None,
    tracer_provider: TracerProvider,
    **kwargs: Unpack[MySQLInstrumentKwargs],
) -> MySQLConnection:
    """Instrument the `mysql` module or a specific MySQL connection so that spans are automatically created for each operation.

    See the `Logfire.instrument_mysql` method for details.
    """
    if conn is not None:
        return MySQLInstrumentor().instrument_connection(conn, tracer_provider=tracer_provider)  # type: ignore[reportUnknownMemberType]
    return MySQLInstrumentor().instrument(**kwargs, tracer_provider=tracer_provider)  # type: ignore[reportUnknownMemberType]
