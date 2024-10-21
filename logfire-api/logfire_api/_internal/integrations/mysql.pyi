from mysql.connector.abstracts import MySQLConnectionAbstract
from mysql.connector.pooling import PooledMySQLConnection
from opentelemetry.trace import TracerProvider
from typing_extensions import TypeVar, TypedDict, Unpack

MySQLConnection = TypeVar('MySQLConnection', bound=PooledMySQLConnection | MySQLConnectionAbstract | None)

class MySQLInstrumentKwargs(TypedDict, total=False):
    skip_dep_check: bool

def instrument_mysql(*, conn: MySQLConnection = None, tracer_provider: TracerProvider, **kwargs: Unpack[MySQLInstrumentKwargs]) -> MySQLConnection:
    """Instrument the `mysql` module or a specific MySQL connection so that spans are automatically created for each operation.

    See the `Logfire.instrument_mysql` method for details.
    """
