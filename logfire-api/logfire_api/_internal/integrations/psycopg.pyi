from _typeshed import Incomplete
from logfire import Logfire as Logfire
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from typing import Any
from typing_extensions import TypedDict, Unpack

Instrumentor = PsycopgInstrumentor | Psycopg2Instrumentor

class CommenterOptions(TypedDict, total=False):
    db_driver: bool
    db_framework: bool
    opentelemetry_values: bool

class PsycopgInstrumentKwargs(TypedDict, total=False):
    enable_commenter: bool
    commenter_options: CommenterOptions

PACKAGE_NAMES: Incomplete

def instrument_psycopg(logfire_instance: Logfire, conn_or_module: Any = None, **kwargs: Unpack[PsycopgInstrumentKwargs]) -> None:
    """Instrument a `psycopg` connection or module so that spans are automatically created for each query.

    See the `Logfire.instrument_psycopg` method for details.
    """
def check_version(name: str, version: str, instrumentor: Instrumentor) -> bool: ...
