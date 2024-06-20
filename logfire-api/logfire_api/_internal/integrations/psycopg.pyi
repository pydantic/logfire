from _typeshed import Incomplete
from typing import Any

Instrumentor: Incomplete
PACKAGE_NAMES: Incomplete

def instrument_psycopg(conn_or_module: Any = None, **kwargs: Any):
    """Instrument a `psycopg` connection or module so that spans are automatically created for each query.

    See the `Logfire.instrument_psycopg` method for details.
    """
def check_version(name: str, version: str, instrumentor: Instrumentor): ...
