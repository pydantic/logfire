from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry.instrumentation.mysql import MySQLInstrumentor

if TYPE_CHECKING:
    from mysql.connector.abstracts import MySQLConnectionAbstract
    from mysql.connector.pooling import PooledMySQLConnection
    from typing_extensions import TypedDict, TypeVar, Unpack

    MySQLConnection = TypeVar('MySQLConnection', bound=PooledMySQLConnection | MySQLConnectionAbstract | None)

    class MySQLInstrumentKwargs(TypedDict, total=False):
        skip_dep_check: bool


def instrument_mysql(
    conn: MySQLConnection = None,
    **kwargs: Unpack[MySQLInstrumentKwargs],
) -> MySQLConnection:
    """Instrument the `mysql` module or a specific MySQL connection so that spans are automatically created for each operation.

    This function uses the OpenTelemetry MySQL Instrumentation library to instrument either the entire `mysql` module or a specific MySQL connection.

    Args:
        conn: The MySQL connection to instrument. If None, the entire `mysql` module is instrumented.
        **kwargs: Additional keyword arguments to pass to the OpenTelemetry `instrument` methods.

    Returns:
        If a connection is provided, returns the instrumented connection. If no connection is provided, returns None.

    See the `Logfire.instrument_mysql` method for details.
    """
    if conn is not None:
        return MySQLInstrumentor().instrument_connection(conn)  # type: ignore[reportUnknownMemberType]
    return MySQLInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
